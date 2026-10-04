"""Every file a worker writes goes through here: tier and path rules, dry-run by default."""

from __future__ import annotations

import json
from pathlib import Path

from ..core.errors import TierViolation


class Writer:
    def __init__(self, root: Path, writes: list[str], tier: str, apply: bool):
        self.root = Path(root).resolve()
        self.allowed = [(self.root / w).resolve() for w in writes]
        self.tier = tier
        self.apply = apply
        self.planned: list[tuple[str, int]] = []   # (relative path, rows)
        self.written: list[str] = []

    def _check(self, rel: str) -> Path:
        if self.tier == "T0":
            raise TierViolation("T0 workers only notify; they may not write files")
        target = (self.root / rel).resolve()
        if not any(target == a or a in target.parents for a in self.allowed):
            raise TierViolation(f"{rel} is outside the paths this worker declares in 'writes'")
        return target

    def write_jsonl(self, rel: str, rows: list[dict]) -> None:
        target = self._check(rel)
        self.planned.append((rel, len(rows)))
        if not self.apply:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.written.append(rel)
