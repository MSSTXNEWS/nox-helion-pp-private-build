#!/usr/bin/env bash
set -euo pipefail
# This monitor alone does NOT train or allocate GPU. Start ONLY after explicit
# operator activation, and attach native OneHost STOP callback before live use.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
OUT="${NOX_V37_REPORT_DIR:-$HOME/nox_v37_reports}"
mkdir -p "$OUT"
exec python -m nox_v37.continuous --workspace "${NOX_WORKSPACE:-/workspace}" \
  --loop --interval 30 --log "$OUT/telemetry.jsonl" --stop-flag "$OUT/STOP"
