#!/usr/bin/env bash
set -euo pipefail
umask 077

if (( $# >= 1 )) && [[ "$1" == "--worker" ]]; then
  if (( $# != 2 )); then
    echo "worker requires exit-file path" >&2
    exit 64
  fi
  EXIT_FILE="$2"
  set +e
  (
    set -euo pipefail
    mkdir -p /root/nox/in_v6
    cd /root/nox/in_v6
    pip install -q -U gdown
    gdown 1zl20T5qy9A7tIU2GKTV1kIsCA1ahR2aj -O NOX_V7_BRAIN_v6.zip.part00.bin
    gdown 1gYucZQr4VizHgxcmVuey7JflgK8Drpxr -O NOX_V7_BRAIN_v6.zip.part01.bin
    cat NOX_V7_BRAIN_v6.zip.part00.bin NOX_V7_BRAIN_v6.zip.part01.bin > NOX_V7_BRAIN_v6_20261122.zip
    printf '%s  %s\n' 95b9effdf88d04b1d517aeaf3adca21860eceb29270eb68ebadeb4b995750a4a NOX_V7_BRAIN_v6_20261122.zip | sha256sum -c -
    unzip -q -o NOX_V7_BRAIN_v6_20261122.zip -d /root/nox/v7_src_v6
    test -d /root/nox/v7_src_v6/nox_wow
    ls /root/nox/v7_src_v6/nox_wow | head -n 50 || true
    df -h /root /dev/shm
    free -g
  )
  RC=$?
  set -e
  printf '%s\n' "$RC" > "$EXIT_FILE.tmp"
  mv -- "$EXIT_FILE.tmp" "$EXIT_FILE"
  exit "$RC"
fi

RUN_ID="$(basename "$0" .worker.sh)"
BASE="/root/nox/logs/$RUN_ID"
LOG="$BASE.log"
PID_FILE="$BASE.pid"
EXIT_FILE="$BASE.exit"
mkdir -p /root/nox/logs
if [[ -e "$LOG" || -e "$PID_FILE" || -e "$EXIT_FILE" ]]; then
  echo "Refusing to reuse existing run files for $RUN_ID" >&2
  exit 73
fi
nohup bash "$0" --worker "$EXIT_FILE" </dev/null >>"$LOG" 2>&1 &
PID=$!
printf '%s\n' "$PID" > "$PID_FILE"
printf 'STARTED run_id=%s pid=%s log=%s exit=%s\n' "$RUN_ID" "$PID" "$LOG" "$EXIT_FILE"
