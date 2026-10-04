import pytest

from grounded_agents.core.states import Item, State
from grounded_agents.core.steps import step_draft, step_filter, step_ground, step_verify
from helpers import FAIL, GOOD, INSUFFICIENT, PASS, UNCITED, make_ctx

Q = "Do you encrypt customer data at rest?"


def run_once(ctx, item):
    draft = step_draft(item, ctx)
    if draft is not None and step_ground(item, ctx):
        step_verify(item, ctx)
    return item


def test_filter_moves_out():
    ctx, _ = make_ctx({})
    item = Item("q", "What is your price per seat?")
    step_filter(item, ctx)
    assert (item.state, item.reason) == (State.FILTERED_OUT, "pricing")


def test_first_try_approval():
    ctx, fake = make_ctx({"items": {"q": {"drafter": [GOOD], "verifier": [PASS]}}})
    item = run_once(ctx, Item("q", Q))
    assert item.state is State.APPROVED and item.attempts == 1
    assert [r.role for r in fake.requests] == ["drafter", "verifier"]


def test_insufficient_evidence_goes_to_human_without_retry():
    ctx, fake = make_ctx({"items": {"q": {"drafter": [INSUFFICIENT]}}})
    item = run_once(ctx, Item("q", Q))
    assert (item.state, item.reason) == (State.NEEDS_HUMAN, "insufficient_evidence")
    assert len(fake.requests) == 1


def test_grounding_failure_skips_verifier():
    ctx, fake = make_ctx({"items": {"q": {"drafter": [UNCITED]}}})
    item = run_once(ctx, Item("q", Q))
    assert item.state is State.GROUNDING_FAILED
    assert item.objections[-1][0].rule == "grounding:quote_not_found"
    assert [r.role for r in fake.requests] == ["drafter"]


def test_invalid_output_counts_as_attempt():
    ctx, _ = make_ctx({"items": {"q": {"drafter": [{"_raw": "Sure! Yes we do."}]}}})
    item = run_once(ctx, Item("q", Q))
    assert item.state is State.GROUNDING_FAILED and item.attempts == 1
    assert item.objections[-1][0].rule == "invalid_output"


def test_pass_with_objections_is_a_fail():
    passing_but = {**FAIL, "verdict": "pass"}
    ctx, _ = make_ctx({"items": {"q": {"drafter": [GOOD], "verifier": [passing_but]}}})
    assert run_once(ctx, Item("q", Q)).state is State.VERIFY_FAILED


def test_unverified_objection_still_blocks():
    made_up = {"verdict": "fail", "objections": [{
        "claim": 0, "rule": "overreach", "source_quote": "Quillmere never encrypts anything",
        "explanation": "invented"}]}
    ctx, _ = make_ctx({"items": {"q": {"drafter": [GOOD], "verifier": [made_up]}}})
    item = run_once(ctx, Item("q", Q))
    assert item.state is State.VERIFY_FAILED
    assert item.objections[-1][0].verified is False


def test_retry_prompt_carries_objections_then_second_failure_needs_human():
    ctx, fake = make_ctx({"items": {"q": {"drafter": [GOOD, GOOD], "verifier": [FAIL, FAIL]}}})
    item = run_once(ctx, Item("q", Q))
    run_once(ctx, item)
    assert item.state is State.NEEDS_HUMAN and item.attempts == 2
    assert "overreach" in item.reason
    retry_prompt = fake.requests[2].user
    assert "Objections to fix" in retry_prompt and "Encryption at rest is enabled by default" in retry_prompt


def test_verify_refuses_ungrounded_draft():
    ctx, _ = make_ctx({"items": {"q": {"drafter": [GOOD], "verifier": [PASS]}}})
    item = Item("q", Q)
    step_draft(item, ctx)
    with pytest.raises(RuntimeError, match="without a grounded draft"):
        step_verify(item, ctx)
