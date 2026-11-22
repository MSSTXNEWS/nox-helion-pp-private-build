#!/usr/bin/env bash
# backup_s03.sh - бэкап S03 (REVIEW_1 п.4.6, исправление 13). Ежечасно (cron/DSP): sqlite3 .backup (консистентно при WAL) -> ротация -> копия
# на ПК/Диск через rclone (если есть и задан NOX_BACKUP_REMOTE) -> квитанция $RECEIPTS/MEM-13.json.
#   backup_s03.sh                  сделать бэкап (ротация: KEEP_HOURLY=48 почасовых + KEEP_DAILY=14 суточных)
#   backup_s03.sh --require-fresh N  код 0, если последний бэкап моложе N секунд (ворота для consolidate --apply)
#   backup_s03.sh --dry-run        ничего не писать, показать план
# Cron (ежечасно): 7 * * * * /root/nox/src/wow7/mem/backup_s03.sh
# Env: S03_DB, BACKUP_DIR, RECEIPTS, NOX_BACKUP_REMOTE (например gdrive:nox_s03), KEEP_HOURLY, KEEP_DAILY.
set -euo pipefail
S03_DB="${S03_DB:-/root/nox/state/s03.sqlite}"
BACKUP_DIR="${BACKUP_DIR:-/root/nox/memory/backups}"
RECEIPTS="${RECEIPTS:-/root/nox/receipts}"
KEEP_HOURLY="${KEEP_HOURLY:-48}"; KEEP_DAILY="${KEEP_DAILY:-14}"
REMOTE="${NOX_BACKUP_REMOTE:-}"
newest() { ls -1t "$BACKUP_DIR"/s03_*.sqlite 2>/dev/null | head -1 || true; }
if [ "${1:-}" = "--require-fresh" ]; then
  f="$(newest)"; [ -n "$f" ] || { echo "бэкапов нет" >&2; exit 1; }
  age=$(( $(date +%s) - $(stat -c %Y "$f") )); [ "$age" -le "${2:-7200}" ] || { echo "последний бэкап старше ${2:-7200} с ($age)" >&2; exit 1; }
  echo "свежий бэкап: $f (${age} с)"; exit 0
fi
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
if [ "$DRY" = 1 ]; then echo "[dry-run] sqlite3 $S03_DB '.backup $BACKUP_DIR/s03_<ts>.sqlite'; ротация $KEEP_HOURLY ч + $KEEP_DAILY сут; rclone -> ${REMOTE:-(не задан)}"; exit 0; fi
[ -f "$S03_DB" ] || { echo "нет базы $S03_DB" >&2; exit 1; }
py_backup() { python3 - "$1" "$2" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1], timeout=10); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
}
py_check() { python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" "$1"; }
mkdir -p "$BACKUP_DIR" "$RECEIPTS"
TS="$(date +%Y%m%d_%H%M)"; OUT="$BACKUP_DIR/s03_$TS.sqlite"
if command -v sqlite3 >/dev/null; then sqlite3 "$S03_DB" ".timeout 10000" ".backup '$OUT.part'"; else py_backup "$S03_DB" "$OUT.part"; fi
mv "$OUT.part" "$OUT"
if command -v sqlite3 >/dev/null; then CHK="$(sqlite3 "$OUT" 'PRAGMA integrity_check;' | head -1)"; else CHK="$(py_check "$OUT")"; fi
[ "$CHK" = "ok" ] || { rm -f "$OUT"; echo "integrity_check: $CHK" >&2; python3 -c "import json,sys,time;json.dump({'id':'MEM-13','status':'fail','detail':sys.argv[1],'ts':time.strftime('%FT%T%z')},open(sys.argv[2],'w'),ensure_ascii=False)" "integrity: $CHK" "$RECEIPTS/MEM-13.json"; exit 1; }
SHA="$(sha256sum "$OUT" | cut -d' ' -f1)"; SIZE="$(stat -c %s "$OUT")"
# ротация: суточные = первый бэкап каждых суток (s03_YYYYMMDD_00xx), почасовые - последние KEEP_HOURLY
ls -1t "$BACKUP_DIR"/s03_*.sqlite | tail -n +$((KEEP_HOURLY + 1)) | while read -r f; do
  d="$(basename "$f" | cut -d_ -f2)"; first="$(ls -1 "$BACKUP_DIR"/s03_${d}_*.sqlite | head -1)"
  if [ "$f" = "$first" ] && [ "$(ls -1 "$BACKUP_DIR"/s03_*_*.sqlite | cut -d_ -f2 | sort -u | wc -l)" -le "$KEEP_DAILY" ]; then continue; fi
  rm -f "$f"
done
REM="нет (NOX_BACKUP_REMOTE не задан)"
if [ -n "$REMOTE" ] && command -v rclone >/dev/null; then
  if rclone copyto "$OUT" "$REMOTE/$(basename "$OUT")" --retries 2 >/dev/null 2>&1; then REM="ok $REMOTE"; else REM="ОШИБКА rclone $REMOTE"; fi
fi
python3 - "$RECEIPTS/MEM-13.json" "$OUT" "$SHA" "$SIZE" "$REM" <<'PY'
import json, sys, time
p, out, sha, size, rem = sys.argv[1:6]
json.dump({"id": "MEM-13", "status": "ok" if not rem.startswith("ОШИБКА") else "warn", "file": out, "sha256": sha, "bytes": int(size),
           "remote": rem, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, open(p, "w"), ensure_ascii=False)
PY
echo "бэкап S03: $OUT ($SIZE байт), удалённая копия: $REM"
