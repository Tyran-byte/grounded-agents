"""``grounded`` command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core.budget import Budget
from .core.errors import GroundedError
from .core.states import State
from .evals import gate, seal
from .runtime import ledger
from .runtime.alerts import StdoutNotifier, WebhookNotifier
from .runtime.context import build_context, fake_models, models_fingerprint, provider_kind
from .runtime.manifest import load_manifest, resolve_models
from .runtime.runner import LEDGER, run_worker


def _print_items(items) -> None:
    for item in items:
        line = f"  {item.id:<8} {item.state.value:<13} attempts={item.attempts}"
        if item.reason:
            line += f"  ({item.reason})"
        print(line)


def cmd_run(args) -> int:
    root = Path(args.root)
    notifier = WebhookNotifier(os.environ["GA_ALERT_WEBHOOK"]) if os.environ.get(
        "GA_ALERT_WEBHOOK") else StdoutNotifier()
    try:
        manifest = load_manifest(args.manifest)
    except GroundedError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    result = run_worker(manifest, root=root, apply=args.apply, provider=args.provider,
                        script=args.script, approved_by=args.approved_by, notifier=notifier)
    print(f"{manifest.name} [{manifest.engine}, {manifest.tier}, {result.mode}] "
          f"trace={result.trace_id}")
    _print_items(result.items)
    for path, rows in result.planned:
        verb = "wrote" if result.mode == "apply" else "would write"
        print(f"  {verb} {rows} row(s) to {path}")
    print(f"  calls={result.calls} cost_usd={result.cost_usd:.6f} exit={result.exit_code}")
    if result.error:
        print(f"  error: {result.error}", file=sys.stderr)
    return result.exit_code


def cmd_schedule(args) -> int:
    root = Path(args.root).resolve()
    for path in sorted((root / "workers").glob("*.toml")):
        m = load_manifest(path)
        if m.schedule:
            print(f"{m.schedule} cd {root} && grounded run {path.relative_to(root)} --apply"
                  f"  # {m.name} ({m.tier})")
    return 0


def cmd_ledger(args) -> int:
    for row in ledger.read(Path(args.root) / LEDGER)[-args.n:]:
        print(json.dumps(row, sort_keys=True))
    return 0


def _eval_context(args, budget_spec: dict):
    root = Path(args.root)
    if args.provider == "fake":
        models = fake_models()
        script = args.script or root / "evals" / "fake-script.json"
    else:
        models = resolve_models(load_manifest(args.manifest), None)
        script = None
    budget = Budget(float(budget_spec.get("per_call_usd", 0.05)),
                    float(budget_spec.get("per_run_usd", 2.0)),
                    float(budget_spec.get("per_run_usd", 2.0)))
    return build_context(root, models, budget, script), models


def cmd_evals(args) -> int:
    root = Path(args.root)
    evals_dir = root / "evals"
    try:
        if args.evals_cmd == "freeze":
            lock = seal.freeze(evals_dir, new_version=args.new_version)
            print(f"eval set v{lock['version']} frozen: {lock['set_hash'][:16]}")
            return 0
        seal.check_frozen(evals_dir)
        header, cases = gate.load_set(evals_dir)
        ctx, models = _eval_context(args, header.get("budget", {}))
        report = gate.run_gate(cases, header, args.engine, ctx)
    except (GroundedError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if args.evals_cmd == "sample":
        for item in gate.sample(report, args.n, args.seed):
            draft = item.drafts[-1]
            print(f"## {item.id}: {item.question}\n{draft.answer}")
            for claim in draft.claims:
                for c in claim.citations:
                    print(f'  - [{c.source}] "{c.quote}"')
            print()
        return 0
    print(f"engine={args.engine} provider={provider_kind(models)} "
          f"metrics={json.dumps(report.metrics())}")
    for failure in report.failures:
        print(f"  - {failure}")
    if report.stopped is not None:
        return 2
    verdict = "green" if report.green else "red"
    if args.evals_cmd == "seal":
        seal.write_seal(root, args.engine, models_fingerprint(models), provider_kind(models),
                        report.green, report.metrics())
        print(f"sealed {verdict}")
    else:
        print(verdict)
    return 0 if report.green else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grounded", description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run a worker (dry-run unless --apply)")
    run.add_argument("manifest", type=Path)
    run.add_argument("--apply", action="store_true", help="write outputs (needs a green seal)")
    run.add_argument("--provider", choices=["fake"], help="override models with the fake provider")
    run.add_argument("--script", type=Path, help="fake provider script")
    run.add_argument("--approved-by", help="approver name, required to apply a T3 worker")
    run.set_defaults(func=cmd_run)

    sub.add_parser("schedule", help="print crontab lines for scheduled workers").set_defaults(
        func=cmd_schedule)

    led = sub.add_parser("ledger", help="show the last runs")
    led.add_argument("-n", type=int, default=10)
    led.set_defaults(func=cmd_ledger)

    ev = sub.add_parser("evals", help="freeze, seal, check or sample the eval set")
    ev_sub = ev.add_subparsers(dest="evals_cmd", required=True)
    fr = ev_sub.add_parser("freeze")
    fr.add_argument("--new-version", action="store_true")
    for name in ("seal", "check", "sample"):
        p = ev_sub.add_parser(name)
        p.add_argument("--engine", choices=["plain", "langgraph"], default="plain")
        p.add_argument("--provider", choices=["fake", "real"], default="fake")
        p.add_argument("--script", type=Path, help="fake provider script")
        p.add_argument("--manifest", type=Path, default=Path("workers/answer-plain.toml"),
                       help="manifest whose [models] to use with --provider real")
        if name == "sample":
            p.add_argument("n", type=int)
            p.add_argument("--seed", type=int, default=0)
    ev.set_defaults(func=cmd_evals)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
