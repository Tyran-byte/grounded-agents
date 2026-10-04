import pytest

from grounded_agents.core.errors import InvalidTransition
from grounded_agents.core.states import TERMINAL, Item, State


def test_happy_path_records_history():
    item = Item("q1", "Do you encrypt?")
    item.move(State.DRAFTED)
    item.move(State.APPROVED)
    assert item.state is State.APPROVED
    assert item.history == [State.QUEUED, State.DRAFTED, State.APPROVED]


def test_retry_path():
    item = Item("q1", "?")
    for state in (State.DRAFTED, State.VERIFY_FAILED, State.DRAFTED, State.GROUNDING_FAILED,
                  State.NEEDS_HUMAN):
        item.move(state)
    assert item.state in TERMINAL


@pytest.mark.parametrize("path", [
    [State.APPROVED],                          # cannot approve without a draft
    [State.DRAFTED, State.APPROVED, State.DRAFTED],  # terminal is terminal
    [State.FILTERED_OUT, State.DRAFTED],
])
def test_illegal_moves_raise(path):
    item = Item("q1", "?")
    with pytest.raises(InvalidTransition):
        for state in path:
            item.move(state)


def test_reason_is_kept():
    item = Item("q1", "?")
    item.move(State.FILTERED_OUT, "pricing")
    assert item.reason == "pricing"
