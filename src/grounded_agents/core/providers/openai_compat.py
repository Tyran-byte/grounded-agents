"""Any OpenAI-compatible chat-completions endpoint (hosted APIs or local servers), stdlib only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..errors import ProviderUnavailable
from .base import Completion, CompletionRequest, ModelConfig


class OpenAICompatProvider:
    def __init__(self, config: ModelConfig, timeout_s: float = 120):
        if not config.base_url:
            raise ProviderUnavailable("openai_compat needs base_url (e.g. http://host:port/v1)")
        self.config = config
        self.timeout_s = timeout_s

    def complete(self, req: CompletionRequest) -> Completion:
        body = {"model": req.model, "max_tokens": req.max_output_tokens,
                "messages": [{"role": "system", "content": req.system},
                             {"role": "user", "content": req.user}]}
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.config.api_key_env) if self.config.api_key_env else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as err:
            raise ProviderUnavailable(f"openai_compat: HTTP {err.code}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            raise ProviderUnavailable(f"openai_compat: {err}") from None
        try:
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            return Completion(text, int(usage.get("prompt_tokens", 0)),
                              int(usage.get("completion_tokens", 0)))
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable("openai_compat: unexpected response shape") from None
