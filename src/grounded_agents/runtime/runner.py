"""Run one worker under its manifest: tier rules, seal gate, budget, ledger, alerts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ..core.budget import Budget
from ..core.errors import GroundedError, ManifestError, TierViolation
from ..core.schemas import to_jsonable
from ..core.states import Item, State
from ..engines import get_engine
from ..evals.seal import verify_seal
from . import ledger
from .alerts import Notifier, StdoutNotifier, update_alert
from .context import build_context, fake_models, models_fingerprint, provider_kind
from .manifest import Manifest, resolve_models

LEDGER = "ledger/runs.jsonl"
ALERT_STATE = "ledger/alert-state.json"
ANSWERS_DIR = "out/answers"
REVIEW_DIR = "out/review-queue"


@dataclass
class RunResult:
    trace_id: str
    exit_code: int
    mode: str
    items: list[Item] = field(default_factory=list)
    cost_usd: float = 0.0
    calls: int = 0
    error: str = ""
    planned: list[tuple[str, int]] = field(default_factory=list)


def load_questions(root: Path, inputs: list[str]) -> list[Item]:
    items: list[Item] = []
    for rel in inputs:
        base = root / rel
        files = sorted(base.glob("*.jsonl")) if base.is_dir() else [base]
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    items.append(Item(str(row["id"]), str(row["question"])))
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ManifestError("question ids must be unique across inputs")
    return items


def _answer_row(trace_id: str, item: Item) -> dict:
    draft = item.drafts[-1]
    return {"trace_id": trace_id, "id": item.id, "question": item.question,
            "answer": draft.answer, "claims": to_jsonable(draft)["claims"],
            "attempts": item.attempts}


def _review_row(trace_id: str, item: Item) -> dict:
    return {"trace_id": trace_id, "id": item.id, "question": item.question,
            "reason": item.reason, "attempts": item.attempts,
            "drafts": [to_jsonable(d) for d in item.drafts],
            "objections": [[to_jsonable(o) for o in attempt] for attempt in item.objections]}


def run_worker(manifest: Manifest, *, root: Path, apply: bool = False, provider: str | None = None,
               script: Path | None = None, approved_by: str | None = None,
               env: Mapping[str, str] | None = None, now: datetime | None = None,
               notifier: Notifier | None = None) -> RunResult:
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    started = time.monotonic()
    trace_id = ledger.new_trace_id(manifest.name, now)
    result = RunResult(trace_id, 0, "apply" if apply else "dry")
    budget = None
    try:
        if apply and manifest.tier == "T3" and not approved_by:
            raise TierViolation("T3 workers need --approved-by to apply")
        models = fake_models() if provider == "fake" else resolve_models(manifest, env)
        fingerprint, kind = models_fingerprint(models), provider_kind(models)
        if apply:
            verify_seal(root, manifest.engine, fingerprint, kind)
        budget = Budget(manifest.budget.per_call_usd, manifest.budget.per_run_usd,
                        manifest.budget.per_day_usd,
                        ledger.spent_today(root / LEDGER, manifest.name, now.date()))
        ctx = build_context(root, models, budget, script, manifest.timeout_s)
        run = get_engine(manifest.engine)(load_questions(root, manifest.inputs), ctx)
        result.items = run.items
        if manifest.tier != "T0":
            from .writer import Writer
            writer = Writer(root, manifest.writes, manifest.tier, apply)
            approved = [_answer_row(trace_id, i) for i in run.items if i.state is State.APPROVED]
            review = [_review_row(trace_id, i) for i in run.items if i.state is State.NEEDS_HUMAN]
            if approved:
                writer.write_jsonl(f"{ANSWERS_DIR}/{trace_id}.jsonl", approved)
            if review:
                writer.write_jsonl(f"{REVIEW_DIR}/{trace_id}.jsonl", review)
            result.planned = writer.planned
        if run.stopped is not None:
            raise run.stopped
    except (GroundedError, ValueError, OSError) as err:
        result.exit_code = 2
        result.error = f"{type(err).__name__}: {err}"
    if budget is not None:
        result.cost_usd, result.calls = budget.spent_run, budget.calls
    counts: dict[str, int] = {}
    for item in result.items:
        counts[item.state.value] = counts.get(item.state.value, 0) + 1
    ledger.append(root / LEDGER, {
        "worker": manifest.name, "engine": manifest.engine, "tier": manifest.tier,
        "trace_id": trace_id, "mode": result.mode,
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_s": round(time.monotonic() - started, 3), "exit_code": result.exit_code,
        "cost_usd": round(result.cost_usd, 6), "calls": result.calls, "items": counts,
        "approved_by": approved_by, "error": result.error or None})
    if apply:
        update_alert(root / ALERT_STATE, manifest.name, result.exit_code == 0,
                     f"trace {trace_id}: {result.error or 'ok'}", notifier or StdoutNotifier())
    return result
