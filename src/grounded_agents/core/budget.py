"""Spend caps per call, per run and per day.

Checked *before* every call (would the worst-case call fit?) and again after it (did it cost
more than a call is allowed to?). Today's spend from earlier runs comes from the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import BudgetExhausted, CallBudgetExceeded

_EPS = 1e-9


@dataclass
class Budget:
    per_call_usd: float
    per_run_usd: float
    per_day_usd: float
    spent_today_before_run: float = 0.0
    spent_run: float = 0.0
    calls: int = 0

    def check_before_call(self) -> None:
        if self.spent_run + self.per_call_usd > self.per_run_usd + _EPS:
            raise BudgetExhausted("run", f"spent {self.spent_run:.4f} of {self.per_run_usd:.4f} USD")
        today = self.spent_today_before_run + self.spent_run
        if today + self.per_call_usd > self.per_day_usd + _EPS:
            raise BudgetExhausted("day", f"spent {today:.4f} of {self.per_day_usd:.4f} USD")

    def record(self, cost_usd: float) -> None:
        self.spent_run += cost_usd
        self.calls += 1
        if cost_usd > self.per_call_usd + _EPS:
            raise CallBudgetExceeded(cost_usd, self.per_call_usd)
