"""Item states and the only transitions allowed between them."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .errors import InvalidTransition
from .schemas import Draft, Objection


class State(StrEnum):
    QUEUED = "queued"
    FILTERED_OUT = "filtered_out"
    DRAFTED = "drafted"
    GROUNDING_FAILED = "grounding_failed"
    VERIFY_FAILED = "verify_failed"
    APPROVED = "approved"
    NEEDS_HUMAN = "needs_human"


TERMINAL = frozenset({State.FILTERED_OUT, State.APPROVED, State.NEEDS_HUMAN})

TRANSITIONS: dict[State, frozenset[State]] = {
    State.QUEUED: frozenset({State.FILTERED_OUT, State.DRAFTED, State.GROUNDING_FAILED,
                             State.NEEDS_HUMAN}),
    State.DRAFTED: frozenset({State.GROUNDING_FAILED, State.VERIFY_FAILED, State.APPROVED,
                              State.NEEDS_HUMAN}),
    State.GROUNDING_FAILED: frozenset({State.DRAFTED, State.NEEDS_HUMAN}),
    State.VERIFY_FAILED: frozenset({State.DRAFTED, State.NEEDS_HUMAN}),
    State.FILTERED_OUT: frozenset(),
    State.APPROVED: frozenset(),
    State.NEEDS_HUMAN: frozenset(),
}


@dataclass
class Item:
    id: str
    question: str
    state: State = State.QUEUED
    attempts: int = 0
    drafts: list[Draft] = field(default_factory=list)
    objections: list[list[Objection]] = field(default_factory=list)  # one list per attempt
    reason: str = ""
    history: list[State] = field(default_factory=lambda: [State.QUEUED])

    def move(self, to: State, reason: str = "") -> None:
        if to not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.id}: {self.state} -> {to}")
        self.state = to
        self.history.append(to)
        if reason:
            self.reason = reason
