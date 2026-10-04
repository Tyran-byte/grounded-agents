"""Deterministic scripted provider: tests and the offline example run with no key and no network.

Script shape::

    {"items": {"<item id>": {"drafter": [<attempt 1>, <attempt 2>], "verifier": [...]}}}

Responses are indexed by attempt (a ``null`` placeholder marks an attempt that should never
reach that role). Each response is a JSON object (sent back serialized), ``{"_raw": "text"}`` for malformed
output, or ``{"_error": "..."}`` to simulate an outage. ``"_tokens": [in, out]`` overrides the
synthetic token counts so cost and budget paths can be exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import ProviderUnavailable
from .base import Completion, CompletionRequest


class FakeProvider:
    def __init__(self, script: dict):
        self.script = script
        self.requests: list[CompletionRequest] = []

    @classmethod
    def from_file(cls, path: Path | str) -> "FakeProvider":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def complete(self, req: CompletionRequest) -> Completion:
        self.requests.append(req)
        try:
            response = self.script["items"][req.item_id][req.role][req.attempt - 1]
        except (KeyError, IndexError, TypeError):
            response = None
        if response is None:
            raise ProviderUnavailable(
                f"fake: no scripted {req.role} response for {req.item_id} attempt {req.attempt}"
            ) from None
        response = dict(response)
        if "_error" in response:
            raise ProviderUnavailable(f"fake: {response['_error']}")
        tokens = response.pop("_tokens", None)
        text = response["_raw"] if "_raw" in response else json.dumps(response)
        if tokens is None:
            tokens = [len(req.system + req.user) // 4, len(text) // 4]
        return Completion(text, int(tokens[0]), int(tokens[1]))
