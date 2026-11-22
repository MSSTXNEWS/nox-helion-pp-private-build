#!/usr/bin/env bash
# SELF-01: раскладка модулей самовыражения на сервер, самотест, квитанция. bash deploy_self.sh [--dry-run]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${NOX_SELF_DEST:-/root/nox/src/self}"
RCPT="${NOX_RECEIPTS:-/root/nox/receipts}"
FILES="selfcommon.py voice_designer.py ui_mutator.py tastes.py self_tick.py soundscape.js test_voice_designer.py test_ui_mutator.py test_tastes.py test_self_tick.py test_soundscape.js"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
for f in $FILES; do [ -f "$HERE/$f" ] || { echo "нет файла $f" >&2; exit 2; }; done
if [ $DRY = 1 ]; then echo "dry-run: скопировал бы в $DEST: $FILES; затем unittest + node test; квитанция $RCPT/SELF-01.json"; exit 0; fi
mkdir -p "$DEST" "$RCPT"
for f in $FILES; do cp "$HERE/$f" "$DEST/$f"; done
cd "$DEST"
OK=true; PYOUT=$(python3 -m unittest test_voice_designer test_ui_mutator test_tastes test_self_tick 2>&1 | tail -3) || OK=false
JSOUT="node не найден (soundscape тест пропущен)"
if command -v node >/dev/null 2>&1; then JSOUT=$(node test_soundscape.js 2>&1 | tail -1) || OK=false; fi
printf '{"id":"SELF-01","ok":%s,"dest":"%s","python":"%s","js":"%s","ts":%s}\n' "$OK" "$DEST" "$(echo "$PYOUT" | tr '\n"' ' ')" "$(echo "$JSOUT" | tr '"' ' ')" "$(date +%s)" > "$RCPT/SELF-01.json"
cat "$RCPT/SELF-01.json"; [ "$OK" = true ]
