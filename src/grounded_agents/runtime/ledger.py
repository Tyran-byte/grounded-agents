"""Append-only JSONL ledger: one line per run, enough to answer "what ran, what did it cost"."""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timezone
from pathlib import Path


def new_trace_id(worker: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{worker}-{now.astimezone(timezone.utc):%Y%m%dT%H%M%S}-{secrets.token_hex(2)}"


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn last line must not hide every earlier run
    return rows


def spent_today(path: Path, worker: str, day: date) -> float:
    prefix = day.isoformat()
    return sum(float(r.get("cost_usd", 0)) for r in read(path)
               if r.get("worker") == worker and str(r.get("started_at", "")).startswith(prefix))
