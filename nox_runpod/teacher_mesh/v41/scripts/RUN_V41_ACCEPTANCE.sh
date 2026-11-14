#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
echo "NOX V41 source acceptance — not a live training restart"
python3 scripts/VERIFY_SOURCE.py
python3 -m compileall -q training nox_runpod/teacher_mesh/v37 nox_runpod/teacher_mesh/v38 nox_runpod/teacher_mesh/v39
PYTHONPATH="$HERE" python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH="$HERE" python3 -m unittest nox_runpod.teacher_mesh.v37.tests.test_v37 nox_runpod.teacher_mesh.v38.tests.test_v38_control nox_runpod.teacher_mesh.v38.tests.test_v38_memory_speed -v
node --check web/nox-learning-3axes.js
python3 training/preflight_stack.py
python3 training/proof_metrics.py --evidence training/NOX_EVIDENCE_HOLD.json
printf 'HOLD: live OneHost, checkpoints and backup must be independently verified before restart.\n'
