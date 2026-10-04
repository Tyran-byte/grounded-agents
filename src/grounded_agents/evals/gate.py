"""Deterministic eval gate over a frozen case set, plus a qualitative sample for a human read."""

from __future__ import annotations

import json
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..core.errors import GroundedError
from ..core.grounding import check_draft
from ..core.states import Item, State
from ..core.steps import Context
from ..engines import get_engine

EXPECTED = {"approved", "needs_human", "filtered_out"}


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    expected: str
    must_cite: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()


@dataclass
class GateReport:
    total: int = 0
    correct: int = 0
    ungrounded_shipped: int = 0
    forbidden_hits: int = 0
    failures: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    green: bool = False
    stopped: GroundedError | None = None

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def metrics(self) -> dict:
        return {"total": self.total, "correct": self.correct,
                "accuracy": round(self.accuracy, 4),
                "ungrounded_shipped": self.ungrounded_shipped,
                "forbidden_hits": self.forbidden_hits}


def load_set(evals_dir: Path) -> tuple[dict, list[Case]]:
    header = tomllib.loads((evals_dir / "set.toml").read_text(encoding="utf-8"))
    cases: list[Case] = []
    for path in sorted((evals_dir / "cases").glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("expected") not in EXPECTED:
                raise ValueError(f"{path.name}:{n}: expected must be one of {sorted(EXPECTED)}")
            cases.append(Case(row["id"], row["question"], row["expected"],
                              tuple(row.get("must_cite", ())),
                              tuple(row.get("must_not_contain", ()))))
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in the eval set")
    return header, cases


def run_gate(cases: list[Case], header: dict, engine: str, ctx: Context) -> GateReport:
    result = get_engine(engine)([Item(c.id, c.question) for c in cases], ctx)
    report = GateReport(total=len(cases), items=result.items, stopped=result.stopped)
    if result.stopped is not None:
        report.failures.append(f"run stopped: {type(result.stopped).__name__}: {result.stopped}")
        return report
    for case, item in zip(cases, result.items):
        ok = item.state.value == case.expected
        if not ok:
            report.failures.append(f"{case.id}: expected {case.expected}, got {item.state.value}")
        if item.state is State.APPROVED:
            draft = item.drafts[-1]
            if check_draft(draft, ctx.corpus):  # defence in depth: re-check what shipped
                report.ungrounded_shipped += 1
                report.failures.append(f"{case.id}: shipped an ungrounded claim")
            cited = {c.source for claim in draft.claims for c in claim.citations}
            missing = [s for s in case.must_cite if s not in cited]
            if missing:
                ok = False
                report.failures.append(f"{case.id}: did not cite {', '.join(missing)}")
            text = " ".join([draft.answer] + [c.text for c in draft.claims]).lower()
            hits = [s for s in case.must_not_contain if s.lower() in text]
            if hits:
                report.forbidden_hits += len(hits)
                report.failures.append(f"{case.id}: shipped forbidden text {hits}")
        report.correct += ok
    report.green = (report.accuracy >= float(header.get("accuracy_min", 1.0))
                    and report.ungrounded_shipped == 0 and report.forbidden_hits == 0)
    return report


def sample(report: GateReport, n: int, seed: int = 0) -> list[Item]:
    shipped = [i for i in report.items if i.state is State.APPROVED]
    return random.Random(seed).sample(shipped, min(n, len(shipped)))
