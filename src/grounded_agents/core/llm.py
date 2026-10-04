"""The only path to a model: budget check, call, cost accounting."""

from __future__ import annotations

from dataclasses import dataclass, field

from .budget import Budget
from .providers.base import Completion, CompletionRequest, ModelConfig, Provider


def cost_of(model: ModelConfig, completion: Completion) -> float:
    return (completion.input_tokens * model.price_in_per_mtok
            + completion.output_tokens * model.price_out_per_mtok) / 1_000_000


@dataclass
class LLM:
    providers: dict[str, Provider]   # by role
    models: dict[str, ModelConfig]   # by role
    budget: Budget
    calls_by_role: dict[str, int] = field(default_factory=dict)

    def call(self, role: str, system: str, user: str, *, item_id: str, attempt: int) -> Completion:
        self.budget.check_before_call()
        model = self.models[role]
        completion = self.providers[role].complete(CompletionRequest(
            role=role, model=model.model, system=system, user=user, item_id=item_id,
            attempt=attempt))
        self.calls_by_role[role] = self.calls_by_role.get(role, 0) + 1
        self.budget.record(cost_of(model, completion))
        return completion
