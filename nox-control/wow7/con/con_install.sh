#!/usr/bin/env bash
# CON-04: установка живой я-модели + рабочего пространства + внутреннего цикла на S1.
# Использование: con_install.sh [--dry-run] [--start]   (SRC=каталог с py-файлами, по умолчанию рядом со скриптом)
set -euo pipefail
DRY=0; START=0
for a in "$@"; do case "$a" in --dry-run) DRY=1;; --start) START=1;; *) echo "неизвестный флаг $a" >&2; exit 2;; esac; done
SRC="${SRC:-$(cd "$(dirname "$0")" && pwd)}"
DST="${DST:-/root/nox/src/con}"; RCPT_DIR="${RCPT_DIR:-/root/nox/receipts}"; STATE="${STATE:-/root/nox/state}"
FILES="nox_self_model_live.py nox_workspace.py nox_inner_loop.py test_con.py"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$@"; fi; }
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "нет файла $SRC/$f" >&2; exit 1; }; done
run "mkdir -p '$DST' '$RCPT_DIR' '$STATE'"
for f in $FILES; do run "install -m 0644 '$SRC/$f' '$DST/$f'"; done
if [ "$DRY" = 1 ]; then echo "[dry-run] (cd $DST && python3 -m unittest test_con)"; TESTS=skipped
else (cd "$DST" && python3 -m unittest test_con >/tmp/con_tests.log 2>&1) && TESTS=ok || { cat /tmp/con_tests.log; echo "тесты красные, откат"; for f in $FILES; do rm -f "$DST/$f"; done; exit 1; }; fi
STARTED=no
if [ "$START" = 1 ]; then
  run "pkill -f 'nox_inner_loop.py --daemon' || true"
  run "cd '$DST' && nohup python3 nox_inner_loop.py --daemon --interval 300 >>/root/nox/logs/con_inner.log 2>&1 &"
  STARTED=yes
fi
RC="$RCPT_DIR/CON-04.json"
BODY=$(printf '{"id":"CON-04","ts":"%s","dry_run":%s,"tests":"%s","started":"%s","dst":"%s"}' "$(date -u +%FT%TZ)" "$([ $DRY = 1 ] && echo true || echo false)" "$TESTS" "$STARTED" "$DST")
if [ "$DRY" = 1 ]; then echo "[dry-run] квитанция $RC: $BODY"; else echo "$BODY" > "$RC"; echo "ok: $RC"; fi
