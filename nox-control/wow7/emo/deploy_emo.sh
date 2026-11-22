#!/usr/bin/env bash
# EMO-01: раскладка модулей эмоций на S1 + тесты + квитанция. Использование: deploy_emo.sh [--dry-run] [SRC_DIR]
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
SRC="${1:-$(cd "$(dirname "$0")" && pwd)}"
DST="${NOX_ROOT:-/root/nox}/src/emo"; REC="${NOX_ROOT:-/root/nox}/receipts/EMO-01.json"
FILES="appraisal.py mood.py drives.py emotion_pad.py affect_loop.py mood_ui.py test_emo.py"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "нет $SRC/$f" >&2; exit 2; }; done
run mkdir -p "$DST" "$(dirname "$REC")" "${NOX_ROOT:-/root/nox}/state"
for f in $FILES; do run cp "$SRC/$f" "$DST/$f"; done
if [ "$DRY" = 1 ]; then echo "[dry-run] cd $DST && python3 -m unittest test_emo"; echo "[dry-run] квитанция $REC"; exit 0; fi
OUT=$(cd "$DST" && python3 -m unittest test_emo 2>&1 | tail -3); echo "$OUT"
OK=false; echo "$OUT" | grep -q '^OK' && OK=true
printf '{"id":"EMO-01","ok":%s,"dst":"%s","ts":"%s"}\n' "$OK" "$DST" "$(date -u +%FT%TZ)" > "$REC"
[ "$OK" = true ]
