#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m unittest brain.tests brain.test_v33 brain.test_v34 brain.test_forge_v34 brain.test_stage_v34 -v
printf 'V34 source verification PASS; no production changes.\n'
