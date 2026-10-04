"""The pipeline's steps. Engines decide the order; these functions own every control.

Each step moves an item through the transition table in ``states.py``. An engine that skips
the grounding step cannot reach ``approved``: only ``step_verify`` approves, and it refuses a
draft that has not passed grounding in the same attempt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import schemas
from .corpus import Corpus
from .errors import InvalidOutput
from .filters import filter_question
from .grounding import check_draft, verify_objections
from .llm import LLM
from .prompts import Prompts, build_drafter, build_verifier
from .schemas import Draft, Objection, Verdict
from .states import TRANSITIONS, Item, State


@dataclass
class Context:
    corpus: Corpus
    llm: LLM
    prompts: Prompts
    max_attempts: int = 2
    seen: set[str] = field(default_factory=set)
    parse_draft: Callable[[str], Draft] = schemas.parse_draft
    parse_verdict: Callable[[str], Verdict] = schemas.parse_verdict
    grounded: set[tuple[str, int]] = field(default_factory=set)  # (item id, attempt) that passed


def fail_attempt(item: Item, failed: State, objections: list[Objection], ctx: Context) -> None:
    item.objections.append(objections)
    if failed in TRANSITIONS[item.state]:
        item.move(failed)
    if item.attempts >= ctx.max_attempts:
        rules = sorted({o.rule for o in objections})
        item.move(State.NEEDS_HUMAN, f"failed {item.attempts} attempts: {', '.join(rules)}")


def step_filter(item: Item, ctx: Context) -> None:
    reason = filter_question(item.question, ctx.seen)
    if reason:
        item.move(State.FILTERED_OUT, reason)


def step_draft(item: Item, ctx: Context) -> Draft | None:
    item.attempts += 1
    previous = item.drafts[-1] if item.drafts else None
    objections = item.objections[-1] if item.objections else None
    system, user = build_drafter(ctx.prompts, item.question, ctx.corpus, previous, objections)
    completion = ctx.llm.call("drafter", system, user, item_id=item.id, attempt=item.attempts)
    try:
        draft = ctx.parse_draft(completion.text)
    except InvalidOutput as err:
        fail_attempt(item, State.GROUNDING_FAILED,
                     [Objection(-1, "invalid_output", "", "; ".join(err.errors), True)], ctx)
        return None
    item.drafts.append(draft)
    item.move(State.DRAFTED)
    if draft.status == "insufficient_evidence":
        item.objections.append([])
        item.move(State.NEEDS_HUMAN, "insufficient_evidence")
        return None
    return draft


def step_ground(item: Item, ctx: Context) -> bool:
    objections = check_draft(item.drafts[-1], ctx.corpus)
    if objections:
        fail_attempt(item, State.GROUNDING_FAILED, objections, ctx)
        return False
    ctx.grounded.add((item.id, item.attempts))
    return True


def step_verify(item: Item, ctx: Context) -> bool:
    if item.state is not State.DRAFTED or (item.id, item.attempts) not in ctx.grounded:
        raise RuntimeError(f"{item.id}: verify called without a grounded draft")
    draft = item.drafts[-1]
    system, user = build_verifier(ctx.prompts, item.question, draft, ctx.corpus)
    completion = ctx.llm.call("verifier", system, user, item_id=item.id, attempt=item.attempts)
    try:
        verdict = ctx.parse_verdict(completion.text)
    except InvalidOutput as err:
        fail_attempt(item, State.VERIFY_FAILED,
                     [Objection(-1, "invalid_verifier_output", "", "; ".join(err.errors), True)],
                     ctx)
        return False
    objections = verify_objections(verdict.objections, ctx.corpus)
    if verdict.verdict == "pass" and not objections:
        item.objections.append([])
        item.move(State.APPROVED)
        return True
    if not objections:  # "fail" with nothing to fix still fails closed
        objections = [Objection(-1, "verifier_rejected", "", "Verifier failed the draft.", None)]
    fail_attempt(item, State.VERIFY_FAILED, objections, ctx)
    return False
