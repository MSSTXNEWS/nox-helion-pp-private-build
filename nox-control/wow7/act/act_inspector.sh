#!/usr/bin/env bash
# ACT-12: часовой «инспектор» — находит зависшие задачи (обрыв процесса) и доводит их с места обрыва; квитанция ACT-12.json.
# Запуск: cron/supervisor раз в час. По умолчанию применяет; --dry-run только показывает. Тихие часы не мешают: инспектор не пишет владельцу.
set -euo pipefail
DRY=0; MIN=60
HOME_DIR="${NOX_ACT_HOME:-/root/nox/state/act}"
RECEIPTS="${NOX_RECEIPTS:-/root/nox/receipts}"
SRC="${NOX_ACT_SRC:-/root/nox/src/act}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --minutes) MIN="$2"; shift ;;
    --home) HOME_DIR="$2"; shift ;;
    --receipts) RECEIPTS="$2"; shift ;;
    --src) SRC="$2"; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
  shift
done
TR="python3 $SRC/task_runner.py --home $HOME_DIR --receipts $RECEIPTS"
STALE=$($TR stale --minutes "$MIN" | python3 -c 'import json,sys; print(" ".join(json.load(sys.stdin)["stale"]))')
RESUMED=""; FAILED=""
for id in $STALE; do
  if [ "$DRY" = 1 ]; then RESUMED="$RESUMED $id"; continue; fi
  if $TR run "$id" >/dev/null; then RESUMED="$RESUMED $id"; else FAILED="$FAILED $id"; fi
done
mkdir -p "$RECEIPTS"
python3 - "$RECEIPTS/ACT-12.json" "$DRY" "$MIN" "$STALE" "$RESUMED" "$FAILED" <<'PY'
import json, sys, time
p, dry, mn, stale, resumed, failed = sys.argv[1:7]
json.dump({"id": "ACT-12", "dry_run": dry == "1", "stale_minutes": int(mn), "stale": stale.split(), "resumed_ok": resumed.split(),
           "resume_not_done": failed.split(), "ts": time.time()}, open(p, "w"), ensure_ascii=False, indent=1)
PY
echo "stale=[$STALE] resumed=[$RESUMED] not_done=[$FAILED] dry=$DRY"
