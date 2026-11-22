#!/usr/bin/env bash
# MEM: установка модулей памяти и «сон памяти». Использование:
#   mem_ctl.sh install [--dry-run]           копирует *.py в $MEM_DST, гоняет тесты, пишет квитанцию MEM-05
#   mem_ctl.sh sleep [--apply] [--dry-run]   consolidate+autobio по S03; без --apply - сухой прогон; только 23:00-08:00 МСК
# Пути (можно переопределить окружением для проверки): NOX_REPO_SRC, MEM_SRC, MEM_DST, S03_DB, RECEIPTS.
set -euo pipefail
CMD="${1:-}"; shift || true
DRY=0; APPLY=0
for a in "$@"; do case "$a" in --dry-run) DRY=1;; --apply) APPLY=1;; *) echo "неизвестный аргумент: $a" >&2; exit 2;; esac; done
MEM_SRC="${MEM_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
NOX_REPO_SRC="${NOX_REPO_SRC:-/root/nox/src/nox-control}"
MEM_DST="${MEM_DST:-$NOX_REPO_SRC/wow7/mem}"
S03_DB="${S03_DB:-/root/nox/state/s03.sqlite}"
RECEIPTS="${RECEIPTS:-/root/nox/receipts}"
COMMON_SRC="${NOX_COMMON_SRC:-$MEM_SRC/../COMMON}"; COMMON_DST="${NOX_COMMON_DST:-$MEM_DST/../common}"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
receipt() { # id status detail
  [ "$DRY" = 1 ] && { echo "[dry-run] квитанция $RECEIPTS/$1.json: $2 $3"; return 0; }
  mkdir -p "$RECEIPTS"
  python3 - "$RECEIPTS/$1.json" "$1" "$2" "$3" <<'PY'
import json, sys, time
p, i, st, d = sys.argv[1:5]
json.dump({"id": i, "status": st, "detail": d, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, open(p, "w"), ensure_ascii=False)
PY
}
case "$CMD" in
  install)
    for f in memcommon correction provenance consolidate autobio life_journal; do [ -f "$MEM_SRC/$f.py" ] || { echo "нет $MEM_SRC/$f.py" >&2; exit 1; }; done
    run mkdir -p "$MEM_DST/tests"
    for f in memcommon correction provenance consolidate autobio life_journal; do run cp "$MEM_SRC/$f.py" "$MEM_DST/$f.py"; done
    run mkdir -p "$COMMON_DST"; for f in statefile quiet fastq datafence lifelink; do run cp "$COMMON_SRC/$f.py" "$COMMON_DST/$f.py"; done
    run cp "$MEM_SRC/tests/test_mem.py" "$MEM_SRC/tests/js_ui_test.js" "$MEM_DST/tests/"
    run mkdir -p "$MEM_DST/web"; run cp "$MEM_SRC/web/nox-web-extras.js" "$MEM_DST/web/nox-web-extras.js"
    if [ "$DRY" = 1 ]; then echo "[dry-run] NOX_REPO=$NOX_REPO_SRC python3 -I -B $MEM_DST/tests/test_mem.py"; receipt MEM-05 dry-run "$MEM_DST"; exit 0; fi
    if NOX_REPO="$NOX_REPO_SRC" python3 -I -B "$MEM_DST/tests/test_mem.py" >/tmp/mem_tests.log 2>&1; then
      receipt MEM-05 ok "тесты зелёные, модули в $MEM_DST"; echo "MEM-05 ok"
    else
      tail -20 /tmp/mem_tests.log >&2; receipt MEM-05 fail "тесты красные, см. /tmp/mem_tests.log"; exit 1
    fi ;;
  sleep)
    QC="$COMMON_SRC/quiet.py"; [ -f "$QC" ] || QC="$COMMON_DST/quiet.py"      # единые тихие часы (COMMON/quiet.py, env NOX_QUIET)
    if [ "${MEM_FORCE_HOURS:-0}" != 1 ] && ! python3 -I -B "$QC" --check; then echo "вне тихих часов (NOX_QUIET, по умолчанию 23-08 МСК), пропуск"; exit 0; fi
    if [ "$APPLY" = 1 ] && [ "$DRY" != 1 ]; then   # без свежего бэкапа S03 (<2 ч) --apply не запускается
      BK="${BACKUP_S03_SH:-$MEM_SRC/backup_s03.sh}"
      "$BK" --require-fresh 7200 || { echo "нет свежего бэкапа S03 (<2 ч): сначала backup_s03.sh" >&2; receipt MEM-06 fail "нет свежего бэкапа"; exit 1; }
    fi
    if [ "$DRY" = 1 ]; then echo "[dry-run] consolidate+autobio по $S03_DB apply=$APPLY"; receipt MEM-06 dry-run "$S03_DB"; exit 0; fi
    [ -f "$S03_DB" ] || { echo "нет базы $S03_DB" >&2; exit 1; }
    cp "$S03_DB" "$S03_DB.pre-sleep.$(date +%Y%m%d)" # откат: вернуть копию
    FLAG=""; [ "$APPLY" = 1 ] && FLAG="--apply"
    cd "$MEM_DST" && PYTHONPATH="$NOX_REPO_SRC" python3 -I -B -c "
import sys; sys.path[:0]=['$MEM_DST','$NOX_REPO_SRC']
from qs6.s03_store import Store
import consolidate, correction, autobio, json
st=Store('$S03_DB'); apply=bool('$FLAG')
rep=consolidate.Consolidator(st, correction.Corrector(st)).run(apply)
if apply: autobio.write_missing(st)
print(json.dumps({'applied':rep['applied'],'episodes':rep['episodes']['episodes'],'new_facts':len(rep['episodes']['facts']),'beliefs':len(rep['beliefs']),'forget_facts':len(rep['forget']['facts']),'forget_episodes':len(rep['forget']['episodes']),'questions':len(rep['questions'])}, ensure_ascii=False))
" | tee /tmp/mem_sleep.log
    receipt MEM-06 ok "apply=$APPLY $(tail -1 /tmp/mem_sleep.log)" ;;
  *) echo "использование: mem_ctl.sh install|sleep [--apply] [--dry-run]" >&2; exit 2 ;;
esac
