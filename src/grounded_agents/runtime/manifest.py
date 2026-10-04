"""Worker manifests: the contract a worker runs under (tier, engine, models, budget, writes)."""

from __future__ import annotations

import os
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..core.errors import ManifestError
from ..core.providers.base import ModelConfig

TIERS = ("T0", "T1", "T2", "T3")
ENGINES = ("plain", "langgraph")
PROVIDERS = ("fake", "anthropic", "openai_compat", "command")
ROLES = ("drafter", "verifier")


@dataclass(frozen=True)
class BudgetSpec:
    per_call_usd: float
    per_run_usd: float
    per_day_usd: float


@dataclass(frozen=True)
class Manifest:
    name: str
    description: str
    engine: str
    tier: str
    schedule: str
    timeout_s: int
    inputs: list[str]
    writes: list[str]
    budget: BudgetSpec
    models: dict[str, dict] = field(default_factory=dict)  # raw [models.<role>] tables
    path: Path | None = None


def load_manifest(path: Path | str) -> Manifest:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ManifestError(f"{path}: {err}") from None
    errors: list[str] = []

    def need(key: str, kind: type, table: Mapping = data, prefix: str = ""):
        value = table.get(key)
        ok = isinstance(value, kind) and not (kind in (int, float) and isinstance(value, bool))
        if not ok:
            errors.append(f"{prefix}{key}: required {kind.__name__}")
        return value

    name = need("name", str)
    description = data.get("description", "")
    engine = need("engine", str)
    if isinstance(engine, str) and engine not in ENGINES:
        errors.append(f"engine: must be one of {', '.join(ENGINES)}")
    tier = need("tier", str)
    if isinstance(tier, str) and tier not in TIERS:
        errors.append(f"tier: must be one of {', '.join(TIERS)}")
    schedule = data.get("schedule", "")
    if schedule and len(str(schedule).split()) != 5:
        errors.append("schedule: must be a 5-field cron expression")
    timeout_s = data.get("timeout_s", 600)
    if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0:
        errors.append("timeout_s: must be a positive integer")
    inputs = data.get("inputs", [])
    writes = data.get("writes", [])
    for key, value in (("inputs", inputs), ("writes", writes)):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"{key}: must be a list of paths")
        elif any(Path(v).is_absolute() or ".." in Path(v).parts for v in value):
            errors.append(f"{key}: paths must be relative and stay inside the project")

    budget_table = data.get("budget")
    budget = None
    if not isinstance(budget_table, dict):
        errors.append("budget: required table")
    else:
        values = []
        for key in ("per_call_usd", "per_run_usd", "per_day_usd"):
            value = budget_table.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                errors.append(f"budget.{key}: must be a positive number")
                value = 0.0
            values.append(float(value))
        budget = BudgetSpec(*values)
        if not errors and not (budget.per_call_usd <= budget.per_run_usd <= budget.per_day_usd):
            errors.append("budget: expected per_call_usd <= per_run_usd <= per_day_usd")

    models = data.get("models", {})
    if not isinstance(models, dict):
        errors.append("models: must be a table")
        models = {}
    for role in ROLES:
        spec = models.get(role)
        if not isinstance(spec, dict) or not isinstance(spec.get("provider"), str):
            errors.append(f"models.{role}.provider: required string")
        elif spec["provider"] not in PROVIDERS + ("env",):
            errors.append(f"models.{role}.provider: must be one of {', '.join(PROVIDERS)} or env")

    if errors:
        raise ManifestError(f"{path}: " + "; ".join(errors))
    return Manifest(name, description, engine, tier, schedule, timeout_s, inputs, writes, budget,
                    models, path)


def resolve_models(manifest: Manifest, env: Mapping[str, str] | None = None) -> dict[str, ModelConfig]:
    """Turn ``[models.<role>]`` into ModelConfig. ``provider = "env"`` reads ``GA_<ROLE>_*``.

    There are no defaults for model ids or prices: a run with an unset model fails here, before
    any call, instead of silently using whatever a library happens to default to.
    """
    env = os.environ if env is None else env
    keys = ("provider", "model", "price_in_per_mtok", "price_out_per_mtok", "base_url",
            "api_key_env", "max_output_tokens", "command", "output", "call_timeout_s")
    out: dict[str, ModelConfig] = {}
    for role in ROLES:
        spec = dict(manifest.models[role])
        if spec["provider"] == "env":
            prefix = f"GA_{role.upper()}_"
            spec = {key: env[prefix + key.upper()] for key in keys if prefix + key.upper() in env}
            if "command" in spec:
                spec["command"] = shlex.split(spec["command"])
        missing = [k for k in ("provider", "model", "price_in_per_mtok", "price_out_per_mtok")
                   if k not in spec]
        if missing:
            raise ManifestError(f"models.{role}: missing {', '.join(missing)} "
                                f"(set them in the manifest or as GA_{role.upper()}_* variables)")
        if spec["provider"] not in PROVIDERS:
            raise ManifestError(f"models.{role}.provider: unknown {spec['provider']!r}")
        if spec["provider"] == "command" and not spec.get("command"):
            raise ManifestError(f"models.{role}: the command provider needs 'command'")
        try:
            out[role] = ModelConfig(
                spec["provider"], str(spec["model"]), float(spec["price_in_per_mtok"]),
                float(spec["price_out_per_mtok"]), spec.get("base_url"), spec.get("api_key_env"),
                int(spec.get("max_output_tokens", 16000)),
                tuple(spec["command"]) if spec.get("command") else None,
                str(spec.get("output", "stdout")), int(spec.get("call_timeout_s", 300)))
        except ValueError:
            raise ManifestError(f"models.{role}: prices, token and timeout limits must be numbers") from None
    return out
