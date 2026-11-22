#!/usr/bin/env bash
# SLP-07 run_night.sh — обёртка ночного цикла на S2: подтянуть состояние с S1 -> sleep_cycle.py -> отправить принятый адаптер на S1.
# Расписание (МСК 23:05 = 20:05 UTC): 5 20 * * *  bash /root/nox/scripts/slp/run_night.sh >> /root/nox/logs/slp_night.log 2>&1
# Окружение: S1_SSH (user@host для rsync, по ключу), S1_STATE (/root/nox/state), NOX_SPINE_GGUF (базовый GGUF спинного мозга на S2), NOX_SELFTOOLS, LLAMA_CPP.
# Флаги: --dry-run (печатает команды, пишет квитанцию SLP-07, sleep_cycle в dry-run), --no-sync.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S2_STATE="${S2_STATE:-/root/nox/state}"; S1_STATE="${S1_STATE:-/root/nox/state}"; S1_SSH="${S1_SSH:-}"
RECEIPTS="${RECEIPTS_DIR:-/root/nox/receipts}"; DRY=0; SYNC=1
for a in "$@"; do case "$a" in --dry-run) DRY=1;; --no-sync) SYNC=0;; *) echo "неизвестный аргумент $a" >&2; exit 2;; esac; done
STATUS=fail; NOTE=""; T0=$(date +%s)
receipt() { mkdir -p "$RECEIPTS" 2>/dev/null || RECEIPTS=/tmp/nox_receipts; mkdir -p "$RECEIPTS"
  python3 - "$RECEIPTS/SLP-07.json" "$STATUS" "$NOTE" "$DRY" "$T0" <<'PY'
import json,sys,time
p,st,n,d,t0=sys.argv[1:6]
json.dump({"id":"SLP-07","status":st,"note":n,"dry_run":d=="1","started":int(t0),"finished":int(time.time())},open(p,"w"),ensure_ascii=False,indent=1)
PY
}
trap receipt EXIT
run() { if [ "$DRY" = 1 ]; then echo "DRY: $*"; else "$@"; fi; }
if [ "$SYNC" = 1 ]; then
  [ -n "$S1_SSH" ] || { [ "$DRY" = 1 ] && echo "DRY: S1_SSH не задан — синхронизация была бы пропущена" || { NOTE="S1_SSH не задан (или --no-sync)"; echo "$NOTE" >&2; exit 1; }; }
  for f in turns.jsonl feedback.jsonl unknown.jsonl owner_facts.jsonl; do
    run rsync -a --timeout=60 "$S1_SSH:$S1_STATE/$f" "$S2_STATE/$f"
  done
fi
export NOX_ADAPTERS="${NOX_ADAPTERS:-$S2_STATE/adapters}"
SC=(python3 "$HERE/sleep_cycle.py" run --state "$S2_STATE" --workdir "$S2_STATE/sleep" --replay-dir "$S2_STATE/sleep/replay" --receipts "$RECEIPTS" --adapters "$NOX_ADAPTERS" --system "${NOX_SOUL:-$HERE/../soul_prompt_ru.txt}" --regress-holdout "$HERE/regress_holdout.jsonl")
[ "$DRY" = 1 ] && SC+=(--dry-run)
"${SC[@]}"; RC=$?
if [ "$RC" != 0 ]; then NOTE="sleep_cycle rc=$RC"; exit "$RC"; fi
if [ "$DRY" = 0 ] && [ "$SYNC" = 1 ] && [ -n "$S1_SSH" ]; then
  GG=$(python3 "$HERE/adapter_registry.py" status | python3 -c "import sys,json;print(json.load(sys.stdin).get('target') or '')")
  [ -n "$GG" ] && run rsync -aL --timeout=600 "$GG" "$S1_SSH:/root/nox/state/adapters/incoming.gguf"
  run rsync -a "$S2_STATE/morning_report.json" "$S1_SSH:$S1_STATE/morning_report.json"
else
  run echo "отправка адаптера и morning_report на S1 пропущена"
fi
STATUS=ok; [ "$DRY" = 1 ] && STATUS=dry-run-ok; NOTE="ночь завершена"; exit 0
