"""The plain engine: the whole pipeline as one readable loop over the shared steps."""

from __future__ import annotations

from ...core.states import TERMINAL, Item
from ...core.steps import Context, step_draft, step_filter, step_ground, step_verify
from .. import EngineResult, run_items


def process_one(item: Item, ctx: Context) -> Item:
    step_filter(item, ctx)
    while item.state not in TERMINAL:
        if step_draft(item, ctx) is None:
            continue  # invalid output or insufficient evidence; state already updated
        if step_ground(item, ctx):
            step_verify(item, ctx)
    return item


def process(items: list[Item], ctx: Context) -> EngineResult:
    return run_items(items, ctx, process_one)
