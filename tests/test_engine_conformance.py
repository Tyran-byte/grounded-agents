import importlib.util

import pytest

from grounded_agents.core.states import Item
from grounded_agents.engines import get_engine
from helpers import make_ctx
from scenarios import SCENARIOS

ENGINES = ["plain"]
if importlib.util.find_spec("langgraph") and importlib.util.find_spec("pydantic"):
    ENGINES.append("langgraph")


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_engine_conformance(engine, scenario):
    ctx, _ = make_ctx(scenario.script, scenario.budget)
    result = get_engine(engine)([Item(i, q) for i, q in scenario.questions], ctx)
    got = {item.id: (item.state.value, item.attempts) for item in result.items}
    assert got == scenario.expected
    assert (type(result.stopped).__name__ if result.stopped else None) == scenario.stopped
    for item_id, history in scenario.history.items():
        item = next(i for i in result.items if i.id == item_id)
        assert [s.value for s in item.history] == history


def test_unknown_engine():
    with pytest.raises(ValueError, match="unknown engine"):
        get_engine("crewai")
