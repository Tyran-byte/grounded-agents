"""Engines sequence the shared steps. They own ordering, never controls."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from ..core.errors import (BudgetExhausted, CallBudgetExceeded, GroundedError, ProviderUnavailable,
                           RunTimeout)
from ..core.states import Item
from ..core.steps import Context

ENGINES = ("plain", "langgraph")
STOPPING = (BudgetExhausted, CallBudgetExceeded, ProviderUnavailable, RunTimeout)


@dataclass
class EngineResult:
    items: list[Item]
    stopped: GroundedError | None = None


def run_items(items: list[Item], ctx: Context, process_one: Callable[[Item, Context], Item]) -> EngineResult:
    """Process items in order. A stopping error leaves the in-flight item and the rest untouched."""
    out: list[Item] = []
    stopped: GroundedError | None = None
    for item in items:
        if stopped is None:
            try:
                out.append(process_one(copy.deepcopy(item), ctx))
                continue
            except STOPPING as err:
                stopped = err
        out.append(item)
    return EngineResult(out, stopped)


def get_engine(name: str) -> Callable[[list[Item], Context], EngineResult]:
    if name == "plain":
        from .plain.engine import process
        return process
    if name == "langgraph":
        from .langgraph.engine import process
        return process
    raise ValueError(f"unknown engine {name!r}; expected one of {', '.join(ENGINES)}")
