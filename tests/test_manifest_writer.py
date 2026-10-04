import pytest

from grounded_agents.core.errors import ManifestError, TierViolation
from grounded_agents.runtime.manifest import load_manifest, resolve_models
from grounded_agents.runtime.writer import Writer
from helpers import ROOT

VALID = """
name = "answer"
engine = "plain"
tier = "T1"
schedule = "0 7 * * 1-5"
inputs = ["data/q"]
writes = ["out/answers"]
[budget]
per_call_usd = 0.05
per_run_usd = 0.5
per_day_usd = 2.0
[models.drafter]
provider = "env"
[models.verifier]
provider = "openai_compat"
model = "local-model"
price_in_per_mtok = 0
price_out_per_mtok = 0
base_url = "http://127.0.0.1:8000/v1"
"""


def manifest_file(tmp_path, text=VALID):
    path = tmp_path / "w.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_manifest(tmp_path):
    m = load_manifest(manifest_file(tmp_path))
    assert (m.name, m.engine, m.tier, m.timeout_s) == ("answer", "plain", "T1", 600)
    assert m.budget.per_run_usd == 0.5


@pytest.mark.parametrize("old,new,message", [
    ('tier = "T1"', 'tier = "T9"', "tier: must be one of"),
    ('engine = "plain"', 'engine = "magic"', "engine: must be one of"),
    ('schedule = "0 7 * * 1-5"', 'schedule = "daily"', "5-field cron"),
    ("per_run_usd = 0.5", "per_run_usd = -1", "budget.per_run_usd"),
    ("per_day_usd = 2.0", "per_day_usd = 0.1", "per_call_usd <= per_run_usd <= per_day_usd"),
    ('writes = ["out/answers"]', 'writes = ["../elsewhere"]', "stay inside the project"),
    ('name = "answer"\n', "", "name: required"),
])
def test_invalid_manifests(tmp_path, old, new, message):
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_file(tmp_path, VALID.replace(old, new)))


def test_bundled_workers_are_valid():
    for path in (ROOT / "workers").glob("*.toml"):
        assert load_manifest(path).tier == "T1"


def test_resolve_models_from_env(tmp_path):
    m = load_manifest(manifest_file(tmp_path))
    env = {"GA_DRAFTER_PROVIDER": "anthropic", "GA_DRAFTER_MODEL": "some-model",
           "GA_DRAFTER_PRICE_IN_PER_MTOK": "1.5", "GA_DRAFTER_PRICE_OUT_PER_MTOK": "7"}
    models = resolve_models(m, env)
    assert (models["drafter"].provider, models["drafter"].price_out_per_mtok) == ("anthropic", 7.0)
    assert models["verifier"].base_url == "http://127.0.0.1:8000/v1"


def test_resolve_models_has_no_defaults(tmp_path):
    with pytest.raises(ManifestError, match="GA_DRAFTER_"):
        resolve_models(load_manifest(manifest_file(tmp_path)), {})


def test_writer_dry_run_writes_nothing(tmp_path):
    writer = Writer(tmp_path, ["out/answers"], "T1", apply=False)
    writer.write_jsonl("out/answers/x.jsonl", [{"a": 1}])
    assert writer.planned == [("out/answers/x.jsonl", 1)]
    assert not (tmp_path / "out").exists()


def test_writer_apply_writes_inside_declared_paths(tmp_path):
    writer = Writer(tmp_path, ["out/answers"], "T1", apply=True)
    writer.write_jsonl("out/answers/x.jsonl", [{"a": 1}, {"a": 2}])
    assert (tmp_path / "out/answers/x.jsonl").read_text().count("\n") == 2


@pytest.mark.parametrize("rel", ["out/other/x.jsonl", "out/answers/../../escape.jsonl",
                                 "out/answers-evil/x.jsonl"])
def test_writer_rejects_undeclared_paths(tmp_path, rel):
    with pytest.raises(TierViolation):
        Writer(tmp_path, ["out/answers"], "T1", apply=True).write_jsonl(rel, [])


def test_t0_cannot_write(tmp_path):
    with pytest.raises(TierViolation, match="T0"):
        Writer(tmp_path, ["out"], "T0", apply=True).write_jsonl("out/x.jsonl", [])
