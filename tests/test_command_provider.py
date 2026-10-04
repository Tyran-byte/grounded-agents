import sys

import pytest

from grounded_agents.core.errors import ProviderUnavailable
from grounded_agents.core.providers.base import CompletionRequest, ModelConfig
from grounded_agents.core.providers.command import CommandProvider

REQ = CompletionRequest(role="drafter", model="m-1", system="SYS", user="USER")
PY = sys.executable


def provider(*argv, output="stdout", timeout=30):
    return CommandProvider(ModelConfig("command", "m-1", 0, 0, command=tuple(argv),
                                       output=output, call_timeout_s=timeout))


def test_stdin_gets_system_and_user_when_system_is_not_an_argument():
    out = provider(PY, "-c", "import sys; print(sys.stdin.read().upper())").complete(REQ)
    assert out.text == "SYS\n\nUSER"


def test_placeholders_and_output_file():
    code = ("import sys; open(sys.argv[3], 'w').write(sys.argv[1] + '|' + sys.argv[2] + '|' "
            "+ sys.stdin.read()); print('noise on stdout')")
    out = provider(PY, "-c", code, "{model}", "{system}", "{output_file}").complete(REQ)
    assert out.text == "m-1|SYS|USER"


def test_result_json_with_usage():
    code = ('import json; print(json.dumps({"result": "{}", '
            '"usage": {"input_tokens": 7, "output_tokens": 3}}))')
    out = provider(PY, "-c", code, output="result-json").complete(REQ)
    assert (out.text, out.input_tokens, out.output_tokens) == ("{}", 7, 3)


@pytest.mark.parametrize("argv,match", [
    ((PY, "-c", "import sys; sys.exit(3)"), "exited 3"),
    (("definitely-not-a-real-command-xyz",), "command not found"),
    ((PY, "-c", "import time; time.sleep(5)"), "timed out"),
])
def test_failures_become_unavailable(argv, match):
    with pytest.raises(ProviderUnavailable, match=match):
        provider(*argv, timeout=1).complete(REQ)


def test_bad_result_json():
    with pytest.raises(ProviderUnavailable, match="result JSON"):
        provider(PY, "-c", "print('not json')", output="result-json").complete(REQ)
