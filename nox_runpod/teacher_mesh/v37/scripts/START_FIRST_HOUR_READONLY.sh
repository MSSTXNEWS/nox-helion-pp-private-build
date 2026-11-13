#!/usr/bin/env bash
set -euo pipefail
# Execute on existing Vast.ai instance after inspecting this script. NO downloads,
# no installation, no service stop, no model replacement or new GPU worker.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
OUT="${NOX_V37_REPORT_DIR:-$HOME/nox_v37_reports}"
mkdir -p "$OUT"
python -m nox_v37.live_inventory --workspace "${NOX_WORKSPACE:-/workspace}" --out "$OUT/first_hour_inventory.json"
python -m nox_v37.continuous --workspace "${NOX_WORKSPACE:-/workspace}" --log "$OUT/first_hour_status.jsonl"
echo "Created: $OUT/first_hour_inventory.json $OUT/first_hour_status.jsonl"
echo 'Status read only. Native chat controller and FORGE must approve any real launch.'
