"""Scripted scenarios every engine must handle identically."""

from dataclasses import dataclass, field

from grounded_agents.core.budget import Budget
from helpers import FAIL, GOOD, INSUFFICIENT, PASS, UNCITED


@dataclass
class Scenario:
    name: str
    questions: list[tuple[str, str]]
    script: dict
    expected: dict[str, tuple[str, int]]       # id -> (final state, attempts)
    stopped: str | None = None                 # error class name
    budget: Budget | None = None
    history: dict[str, list[str]] = field(default_factory=dict)


ENC = "Do you encrypt customer data at rest?"

SCENARIOS = [
    Scenario("first_try", [("a", ENC)],
             {"items": {"a": {"drafter": [GOOD], "verifier": [PASS]}}},
             {"a": ("approved", 1)},
             history={"a": ["queued", "drafted", "approved"]}),
    Scenario("fixed_on_retry", [("a", ENC)],
             {"items": {"a": {"drafter": [UNCITED, GOOD], "verifier": [None, PASS]}}},  # attempt 1 never reaches the verifier
             {"a": ("approved", 2)},
             history={"a": ["queued", "drafted", "grounding_failed", "drafted", "approved"]}),
    Scenario("needs_human", [("a", ENC)],
             {"items": {"a": {"drafter": [GOOD, GOOD], "verifier": [FAIL, FAIL]}}},
             {"a": ("needs_human", 2)},
             history={"a": ["queued", "drafted", "verify_failed", "drafted", "verify_failed",
                            "needs_human"]}),
    Scenario("filtered_and_insufficient", [("a", "What discount do you offer?"),
                                           ("b", "Do you run a 24/7 security operations center?"),
                                           ("c", "do you run a 24/7  security operations center?")],
             {"items": {"b": {"drafter": [INSUFFICIENT]}}},
             {"a": ("filtered_out", 0), "b": ("needs_human", 1), "c": ("filtered_out", 0)}),
    Scenario("invalid_twice", [("a", ENC)],
             {"items": {"a": {"drafter": [{"_raw": "nope"}, {"_raw": "still nope"}]}}},
             {"a": ("needs_human", 2)},
             history={"a": ["queued", "grounding_failed", "needs_human"]}),
    Scenario("budget_stops_run", [("a", ENC), ("b", ENC + " (backups)")],
             {"items": {"a": {"drafter": [{**GOOD, "_tokens": [1000, 100]}],
                              "verifier": [{**PASS, "_tokens": [1000, 100]}]},
                        "b": {"drafter": [GOOD], "verifier": [PASS]}}},
             {"a": ("approved", 1), "b": ("queued", 0)},
             stopped="BudgetExhausted",
             budget=Budget(per_call_usd=0.002, per_run_usd=0.0045, per_day_usd=1)),
    Scenario("provider_down_keeps_item_queued", [("a", ENC), ("b", ENC + " (backups)")],
             {"items": {"a": {"drafter": [GOOD], "verifier": [PASS]},
                        "b": {"drafter": [GOOD], "verifier": [{"_error": "503"}]}}},
             {"a": ("approved", 1), "b": ("queued", 0)},
             stopped="ProviderUnavailable"),
]
