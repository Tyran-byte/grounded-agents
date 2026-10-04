import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from grounded_agents.core.errors import ProviderUnavailable
from grounded_agents.core.providers.anthropic import AnthropicProvider
from grounded_agents.core.providers.base import CompletionRequest, ModelConfig
from grounded_agents.core.providers.openai_compat import OpenAICompatProvider

REQ = CompletionRequest(role="drafter", model="m-1", system="sys", user="hello",
                        max_output_tokens=99)


@pytest.fixture
def stub():
    state = {"status": 200, "body": None, "seen": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["seen"].append((self.path, dict(self.headers), payload))
            body = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/v1"
    yield state
    server.shutdown()


def config(url, key_env=None):
    return ModelConfig("openai_compat", "m-1", 0, 0, base_url=url, api_key_env=key_env)


def test_openai_compat_request_and_usage(stub, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "k-123")
    stub["body"] = {"choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3}}
    completion = OpenAICompatProvider(config(stub["url"], "TEST_KEY")).complete(REQ)
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ("{}", 11, 3)
    path, headers, payload = stub["seen"][0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer k-123"
    assert payload["messages"][0] == {"role": "system", "content": "sys"}
    assert payload["model"] == "m-1" and payload["max_tokens"] == 99


@pytest.mark.parametrize("status", [429, 500, 503])
def test_openai_compat_http_errors(stub, status):
    stub["status"], stub["body"] = status, {"error": "x"}
    with pytest.raises(ProviderUnavailable, match=f"HTTP {status}"):
        OpenAICompatProvider(config(stub["url"])).complete(REQ)


def test_openai_compat_unreachable():
    with pytest.raises(ProviderUnavailable):
        OpenAICompatProvider(config("http://127.0.0.1:9/v1"), timeout_s=2).complete(REQ)


def test_openai_compat_bad_shape(stub):
    stub["body"] = {"unexpected": True}
    with pytest.raises(ProviderUnavailable, match="shape"):
        OpenAICompatProvider(config(stub["url"])).complete(REQ)


class FakeMessages:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise OSError("connection reset")
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="{\"a\": 1}")],
            usage=SimpleNamespace(input_tokens=20, output_tokens=4))


def test_anthropic_provider_maps_request_and_usage():
    messages = FakeMessages()
    provider = AnthropicProvider(ModelConfig("anthropic", "m-1", 1, 1),
                                 client=SimpleNamespace(messages=messages))
    completion = provider.complete(REQ)
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ('{"a": 1}', 20, 4)
    assert messages.calls[0] == {"model": "m-1", "max_tokens": 99, "system": "sys",
                                 "messages": [{"role": "user", "content": "hello"}]}


def test_anthropic_provider_errors_become_unavailable():
    provider = AnthropicProvider(ModelConfig("anthropic", "m-1", 1, 1),
                                 client=SimpleNamespace(messages=FakeMessages(fail=True)))
    with pytest.raises(ProviderUnavailable, match="connection reset"):
        provider.complete(REQ)
