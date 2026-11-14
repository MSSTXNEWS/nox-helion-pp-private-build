#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
printf '\nNOX V40 STAGING ONLY (NO LIVE SERVER MUTATIONS)\n'
python3 -m compileall -q training
PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" python3 -m unittest discover -s tests -p 'test_*.py' -v
node --check web/nox-learning-3axes.js
python3 training/preflight_stack.py
python3 training/proof_metrics.py --evidence training/NOX_EVIDENCE_HOLD.json
printf 'HOLD: no native callbacks, live trainer restart or new weight claim.\n'
