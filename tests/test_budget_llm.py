import pytest

from grounded_agents.core.budget import Budget
from grounded_agents.core.errors import BudgetExhausted, CallBudgetExceeded, ProviderUnavailable
from grounded_agents.core.llm import LLM, cost_of
from grounded_agents.core.providers.base import Completion, CompletionRequest, ModelConfig
from grounded_agents.core.providers.fake import FakeProvider

MODEL = ModelConfig("fake", "fake-model", price_in_per_mtok=1.0, price_out_per_mtok=5.0)


def test_cost_of():
    assert cost_of(MODEL, Completion("x", 1_000_000, 200_000)) == pytest.approx(2.0)


def test_run_cap_checked_before_call():
    budget = Budget(per_call_usd=0.1, per_run_usd=0.25, per_day_usd=10)
    budget.record(0.1)
    budget.record(0.05)
    budget.check_before_call()  # 0.15 + 0.1 fits exactly 0.25
    budget.record(0.05)
    with pytest.raises(BudgetExhausted) as exc:
        budget.check_before_call()
    assert exc.value.scope == "run"


def test_day_cap_counts_earlier_runs():
    budget = Budget(per_call_usd=0.1, per_run_usd=5, per_day_usd=1.0, spent_today_before_run=0.95)
    with pytest.raises(BudgetExhausted) as exc:
        budget.check_before_call()
    assert exc.value.scope == "day"


def test_call_over_cap_is_recorded_then_raised():
    budget = Budget(per_call_usd=0.1, per_run_usd=5, per_day_usd=5)
    with pytest.raises(CallBudgetExceeded):
        budget.record(0.2)
    assert budget.spent_run == pytest.approx(0.2) and budget.calls == 1


SCRIPT = {"items": {"q1": {
    "drafter": [{"status": "insufficient_evidence", "answer": "n/a", "claims": [],
                 "_tokens": [100, 10]},
                {"_raw": "not json"}],
    "verifier": [{"_error": "timeout"}],
}}}


def request(role, attempt, item="q1"):
    return CompletionRequest(role=role, model="m", system="s", user="u", item_id=item,
                             attempt=attempt)


def test_fake_routes_by_role_item_attempt():
    fake = FakeProvider(SCRIPT)
    first = fake.complete(request("drafter", 1))
    assert '"insufficient_evidence"' in first.text and "_tokens" not in first.text
    assert (first.input_tokens, first.output_tokens) == (100, 10)
    assert fake.complete(request("drafter", 2)).text == "not json"


def test_fake_errors():
    fake = FakeProvider(SCRIPT)
    with pytest.raises(ProviderUnavailable, match="timeout"):
        fake.complete(request("verifier", 1))
    with pytest.raises(ProviderUnavailable, match="no scripted"):
        fake.complete(request("drafter", 3))
    with pytest.raises(ProviderUnavailable):
        fake.complete(request("drafter", 1, item="other"))


def test_llm_meters_and_refuses_when_exhausted():
    budget = Budget(per_call_usd=0.001, per_run_usd=0.001, per_day_usd=1)
    fake = FakeProvider(SCRIPT)
    llm = LLM({"drafter": fake}, {"drafter": MODEL}, budget)
    llm.call("drafter", "s", "u", item_id="q1", attempt=1)
    assert budget.spent_run == pytest.approx((100 * 1 + 10 * 5) / 1e6)
    assert llm.calls_by_role == {"drafter": 1}
    with pytest.raises(BudgetExhausted):
        llm.call("drafter", "s", "u", item_id="q1", attempt=2)
    assert len(fake.requests) == 1  # refused before reaching the provider
