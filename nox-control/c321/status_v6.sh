#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/root/nox/logs
PID_FILE="$(find "$LOG_DIR" -maxdepth 1 -type f -name 'v6_download_*.pid' -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1s/^[^ ]* //p')"
if [[ -z "$PID_FILE" ]]; then
  echo "NO_RUN: no v6 download pid file found"
  exit 2
fi
BASE="$(printf '%s\n' "$PID_FILE" | sed 's/\.pid$//')"
LOG="$BASE.log"
EXIT_FILE="$BASE.exit"
PID="$(cat "$PID_FILE")"
RUN_ID="$(basename "$BASE")"

if [[ -s "$EXIT_FILE" ]]; then
  RC="$(cat "$EXIT_FILE")"
  printf 'DONE run_id=%s rc=%s\n' "$RUN_ID" "$RC"
  if [[ -s "$LOG" ]]; then tail -c 3000 "$LOG" || true; fi
  if [[ "$RC" =~ ^[0-9]+$ ]]; then exit "$RC"; fi
  echo "INVALID_EXIT_CODE" >&2
  exit 2
fi

if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
  printf 'RUNNING run_id=%s pid=%s log=%s\n' "$RUN_ID" "$PID" "$LOG"
  if [[ -s "$LOG" ]]; then tail -c 1500 "$LOG" || true; fi
  exit 0
fi

printf 'UNKNOWN run_id=%s pid=%s (no exit-code file)\n' "$RUN_ID" "$PID"
if [[ -s "$LOG" ]]; then tail -c 2000 "$LOG" || true; fi
exit 2
