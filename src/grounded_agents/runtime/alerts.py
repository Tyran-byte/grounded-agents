"""Alerts fire on a change of state, not on every run.

A worker that fails every hour should page once, then stay quiet until it recovers — and say
so once. The first green run ever is silent: nothing changed that anyone needs to know about.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Protocol


class Notifier(Protocol):
    def send(self, title: str, body: str) -> None: ...


class StdoutNotifier:
    def send(self, title: str, body: str) -> None:
        print(f"[alert] {title}\n{body}")


class WebhookNotifier:
    """POSTs ``{"title", "body"}`` as JSON to any endpoint (chat webhook, incident tool...)."""

    def __init__(self, url: str, timeout_s: float = 10):
        self.url = url
        self.timeout_s = timeout_s

    def send(self, title: str, body: str) -> None:
        data = json.dumps({"title": title, "body": body}).encode()
        req = urllib.request.Request(self.url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s):
            pass


def update_alert(state_path: Path, worker: str, ok: bool, message: str, notifier: Notifier) -> bool:
    """Record this run's status; notify only if it differs from the last one. Returns sent?"""
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    current = "ok" if ok else "failing"
    previous = state.get(worker)
    state[worker] = current
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    if previous == current or (previous is None and ok):
        return False
    title = f"{worker}: recovered" if ok else f"{worker}: failing"
    notifier.send(title, message)
    return True
