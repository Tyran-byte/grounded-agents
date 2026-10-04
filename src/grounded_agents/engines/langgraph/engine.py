"""The LangGraph engine: the same pipeline as a StateGraph, with Pydantic-validated outputs.

Nodes are thin wrappers over the shared steps in ``core.steps``; the graph only encodes the
routing. That is the point of the comparison: the framework buys explicit routing, graph
visualisation and an ecosystem (checkpointing, streaming, tracing), but every control that
makes an answer safe to ship still lives outside it.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict

from ...core.states import TERMINAL, Item, State
from ...core.steps import Context, step_draft, step_filter, step_ground, step_verify
from .. import EngineResult, run_items
from .models import parse_draft, parse_verdict


class PipelineState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    item: Item
    grounded: bool = False


def build_graph(ctx: Context):
    def filter_node(state: PipelineState) -> dict:
        step_filter(state.item, ctx)
        return {"item": state.item}

    def draft_node(state: PipelineState) -> dict:
        step_draft(state.item, ctx)
        return {"item": state.item, "grounded": False}

    def ground_node(state: PipelineState) -> dict:
        return {"item": state.item, "grounded": step_ground(state.item, ctx)}

    def verify_node(state: PipelineState) -> dict:
        step_verify(state.item, ctx)
        return {"item": state.item}

    def done_or(next_node: str):
        return lambda state: END if state.item.state in TERMINAL else next_node

    def after_draft(state: PipelineState) -> str:
        if state.item.state in TERMINAL:
            return END
        return "ground" if state.item.state is State.DRAFTED else "draft"

    def after_ground(state: PipelineState) -> str:
        if state.item.state in TERMINAL:
            return END
        return "verify" if state.grounded else "draft"

    graph = StateGraph(PipelineState)
    graph.add_node("filter", filter_node)
    graph.add_node("draft", draft_node)
    graph.add_node("ground", ground_node)
    graph.add_node("verify", verify_node)
    graph.add_edge(START, "filter")
    graph.add_conditional_edges("filter", done_or("draft"), ["draft", END])
    graph.add_conditional_edges("draft", after_draft, ["ground", "draft", END])
    graph.add_conditional_edges("ground", after_ground, ["verify", "draft", END])
    graph.add_conditional_edges("verify", done_or("draft"), ["draft", END])
    return graph.compile()


def process(items: list[Item], ctx: Context) -> EngineResult:
    ctx.parse_draft, ctx.parse_verdict = parse_draft, parse_verdict
    graph = build_graph(ctx)

    def process_one(item: Item, _ctx: Context) -> Item:
        return graph.invoke(PipelineState(item=item))["item"]

    return run_items(items, ctx, process_one)
