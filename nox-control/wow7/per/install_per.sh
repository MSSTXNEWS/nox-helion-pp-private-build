#!/usr/bin/env bash
# PER-01: ставит personality.py/beliefs.py/development.py в /root/nox/src/qs6/per, гоняет тесты, пишет квитанцию.
# Запуск: bash install_per.sh [--dry-run]. Откат: rm -rf /root/nox/src/qs6/per (состояние в /root/nox/state/*.json не трогает).
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${NOX_PER_DST:-/root/nox/src/qs6/per}"
REC_DIR="${NOX_RECEIPTS:-/root/nox/receipts}"
FILES="personality.py beliefs.py development.py test_per.py"
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "нет $SRC/$f" >&2; exit 2; }; done
if [ $DRY -eq 1 ]; then
  echo "[dry-run] копировать: $FILES -> $DST"; echo "[dry-run] python3 -m unittest test_per"; echo "[dry-run] квитанция $REC_DIR/PER-01.json"; exit 0
fi
mkdir -p "$DST" "$REC_DIR"
for f in $FILES; do cp "$SRC/$f" "$DST/$f"; done
OUT="$(cd "$DST" && NOX_QS6_DIR="${NOX_QS6_DIR:-/root/nox/src/qs6}" python3 -m unittest test_per 2>&1 | tail -3)"
OK=false; echo "$OUT" | grep -q '^OK' && OK=true
printf '{"id":"PER-01","ts":"%s","dst":"%s","tests_ok":%s}\n' "$(date -u +%FT%TZ)" "$DST" "$OK" > "$REC_DIR/PER-01.json"
echo "$OUT"; $OK
