"""Freeze the eval set, then seal results against the exact logic that produced them.

Two hashes, two jobs:

* ``set_hash`` — the cases. Frozen in ``SET.lock`` *before* prompts or logic change. Editing the
  set afterwards needs ``freeze --new-version``, which leaves a visible version bump: the set
  cannot be quietly tuned until the pipeline passes.
* ``logic_hash`` — core code, the engine, the prompts and the control documents. A seal is
  valid only while this hash matches; any change to what decides an answer — including the
  facts it is grounded in — invalidates it until the evals run again.

A red result is sealed as red. Applying (writing outputs) requires a green, current seal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import grounded_agents

from ..core.errors import SealError

PACKAGE = Path(grounded_agents.__file__).resolve().parent


def _digest(paths: list[Path], base: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.relative_to(base).as_posix().encode() + b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def set_hash(evals_dir: Path) -> str:
    return _digest([evals_dir / "set.toml", *(evals_dir / "cases").glob("*.jsonl")], evals_dir)


def logic_hash(root: Path, engine: str) -> str:
    files = [*(PACKAGE / "core").rglob("*.py"), PACKAGE / "engines" / "__init__.py",
             *(PACKAGE / "engines" / engine).rglob("*.py")]
    h = hashlib.sha256()
    h.update(_digest(files, PACKAGE).encode())
    h.update(_digest(list((root / "prompts").glob("*.md")), root).encode())
    h.update(_digest(list((root / "data").rglob("controls/*.md")), root).encode())
    return h.hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze(evals_dir: Path, new_version: bool = False) -> dict:
    lock_path = evals_dir / "SET.lock"
    lock = _read(lock_path)
    current = set_hash(evals_dir)
    if lock and lock["set_hash"] == current:
        return lock
    if lock and not new_version:
        raise SealError("the eval set changed since it was frozen; re-freeze with --new-version "
                        "(this is recorded) instead of editing a frozen set")
    lock = {"version": lock.get("version", 0) + 1, "set_hash": current}
    _write(lock_path, lock)
    return lock


def check_frozen(evals_dir: Path) -> dict:
    lock = _read(evals_dir / "SET.lock")
    if not lock:
        raise SealError("the eval set is not frozen; run: grounded evals freeze")
    if lock["set_hash"] != set_hash(evals_dir):
        raise SealError("the eval set differs from SET.lock")
    return lock


def write_seal(root: Path, engine: str, fingerprint: str, kind: str, green: bool, metrics: dict,
               now: datetime | None = None) -> dict:
    evals_dir = root / "evals"
    lock = check_frozen(evals_dir)
    entry = {"set_version": lock["version"], "set_hash": lock["set_hash"],
             "logic_hash": logic_hash(root, engine), "models": fingerprint, "provider_kind": kind,
             "result": "green" if green else "red", "metrics": metrics,
             "sealed_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    seal_path = evals_dir / "SEAL.json"
    seal = _read(seal_path)
    seal.setdefault("seals", {})[f"{engine}/{kind}"] = entry
    _write(seal_path, seal)
    return entry


def verify_seal(root: Path, engine: str, fingerprint: str, kind: str) -> dict:
    """Raise SealError unless a green seal matches this set, logic, engine and models."""
    evals_dir = root / "evals"
    lock = check_frozen(evals_dir)
    entry = _read(evals_dir / "SEAL.json").get("seals", {}).get(f"{engine}/{kind}")
    if entry is None:
        raise SealError(f"no seal for engine {engine!r} with a {kind} provider; "
                        f"run: grounded evals seal --engine {engine}")
    problems = []
    if entry["set_hash"] != lock["set_hash"]:
        problems.append("sealed against a different eval set")
    if entry["logic_hash"] != logic_hash(root, engine):
        problems.append("code, prompts or control documents changed since the seal")
    if entry["models"] != fingerprint:
        problems.append(f"sealed with models {entry['models']}, running with {fingerprint}")
    if entry["result"] != "green":
        problems.append("the seal is red")
    if problems:
        raise SealError("; ".join(problems))
    return entry
