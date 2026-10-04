#!/usr/bin/env bash
# End-to-end run with no API key and no network: the fake provider replays recorded model
# responses, so every control (filter, grounding, verifier, retry, budget, seal, ledger) runs
# for real while the "model" is deterministic.
set -euo pipefail
cd "$(dirname "$0")/.."
G="${GROUNDED:-grounded}"

echo "== 1. Dry run, plain engine: shows what it would write"
"$G" run workers/answer-plain.toml --provider fake --script examples/fake-script.json

echo
echo "== 2. Same questionnaire through the LangGraph engine (needs the langgraph extra)"
if python -c "import langgraph" 2>/dev/null; then
  "$G" run workers/answer-langgraph.toml --provider fake --script examples/fake-script.json
else
  echo "   skipped: pip install 'grounded-agents[langgraph]'"
fi

echo
echo "== 3. The sealed evals still pass for the current code and prompts"
"$G" evals check --engine plain

echo
echo "== 4. Apply: writes answers and a review queue, stamped with the trace id"
"$G" run workers/answer-plain.toml --provider fake --script examples/fake-script.json --apply

echo
echo "== 5. Ledger: one line per run"
"$G" ledger -n 3
