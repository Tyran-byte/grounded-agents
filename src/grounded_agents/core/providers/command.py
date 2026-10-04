"""Any model behind a command-line program (a vendor CLI, a local runner, a wrapper script).

Useful when access comes through a CLI rather than an API key — for example a subscription
that is only reachable through its official command-line client. The argv may contain three
placeholders: ``{model}``, ``{system}`` (the system prompt as an argument) and ``{output_file}``
(a temporary file the program writes its final answer to). The user prompt goes on stdin; if
``{system}`` is not used, the system prompt is prepended to it.

``output = "stdout"`` reads the answer from stdout (or from ``{output_file}`` when present);
``output = "result-json"`` expects a JSON object with the answer in ``result`` and, optionally,
token counts in ``usage.input_tokens`` / ``usage.output_tokens``. Without token counts the call
is recorded with zero tokens, so spend caps cannot see it: say so wherever results are reported.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from ..errors import ProviderUnavailable
from .base import Completion, CompletionRequest, ModelConfig


class CommandProvider:
    def __init__(self, config: ModelConfig):
        if not config.command:
            raise ProviderUnavailable("the command provider needs a command")
        if config.output not in ("stdout", "result-json"):
            raise ProviderUnavailable(f"unknown command output format {config.output!r}")
        self.config = config

    def complete(self, req: CompletionRequest) -> Completion:
        command = self.config.command or ()
        uses_system = any("{system}" in arg for arg in command)
        with tempfile.TemporaryDirectory(prefix="grounded-") as tmp:
            out_file = Path(tmp) / "answer.txt"
            argv = [arg.replace("{model}", req.model).replace("{system}", req.system)
                    .replace("{output_file}", str(out_file)) for arg in command]
            stdin = req.user if uses_system else f"{req.system}\n\n{req.user}"
            try:
                proc = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                                      timeout=self.config.call_timeout_s, cwd=tmp)
            except FileNotFoundError:
                raise ProviderUnavailable(f"command not found: {argv[0]}") from None
            except subprocess.TimeoutExpired:
                raise ProviderUnavailable(
                    f"command timed out after {self.config.call_timeout_s}s") from None
            if proc.returncode != 0:
                tail = proc.stderr.strip().splitlines()[-1:] or ["(no stderr)"]
                raise ProviderUnavailable(f"command exited {proc.returncode}: {tail[0][:200]}")
            uses_file = any("{output_file}" in arg for arg in command)
            raw = out_file.read_text(encoding="utf-8") if uses_file and out_file.exists() else proc.stdout
        if self.config.output == "stdout":
            return Completion(raw.strip(), 0, 0)
        try:
            data = json.loads(raw)
            usage = data.get("usage") or {}
            return Completion(str(data["result"]), int(usage.get("input_tokens", 0)),
                              int(usage.get("output_tokens", 0)))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise ProviderUnavailable("command output is not the expected result JSON") from None
