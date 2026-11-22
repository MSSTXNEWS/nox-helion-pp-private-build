#!/usr/bin/env bash
# WORLD: установка world_feed / advisor_pool / self_atlas. Карточки WORLD-01..09. Использование: world_install.sh [--dry-run] [--src DIR]
set -euo pipefail
DRY=0; SRC="$(cd "$(dirname "$0")" && pwd)"
while [ $# -gt 0 ]; do case "$1" in --dry-run) DRY=1;; --src) SRC="$2"; shift;; *) echo "unknown $1" >&2; exit 2;; esac; shift; done
DEST=/root/nox/src/wow7/world; REC=/root/nox/receipts/WORLD-install.json
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$*"; fi; }
for f in world_feed.py advisor_pool.py self_atlas.py self_atlas_tool.py feeds.json advisors_free.json test_world.py; do
  [ -f "$SRC/$f" ] || { echo "нет $SRC/$f" >&2; exit 1; }; done
run "mkdir -p $DEST /root/nox/state /root/nox/receipts /root/nox/logs"
run "cp $SRC/world_feed.py $SRC/advisor_pool.py $SRC/self_atlas.py $SRC/self_atlas_tool.py $SRC/feeds.json $SRC/advisors_free.json $SRC/test_world.py $DEST/"
CRON='*/30 * * * * root cd '$DEST' && NOX_STATE=/root/nox/state python3 world_feed.py run --beliefs >>/root/nox/logs/world_feed.log 2>&1
7 * * * * root cd '$DEST' && python3 self_atlas.py scan >>/root/nox/logs/self_atlas.log 2>&1'
if [ "$DRY" = 1 ]; then echo "[dry-run] /etc/cron.d/nox-world <<"; echo "$CRON"; else
  # тихие часы 23-08 МСК не нарушаем: сбор новостей - фоновое чтение, без сообщений владельцу
  printf '%s\n' "$CRON" > /etc/cron.d/nox-world; fi
if [ "$DRY" = 0 ]; then
  (cd "$DEST" && python3 -W ignore -m unittest test_world 2>&1 | tail -3) 
  python3 "$DEST/self_atlas.py" scan
  printf '{"id":"WORLD-install","ts":%s,"dest":"%s","ok":true}\n' "$(date +%s)" "$DEST" > "$REC"
else echo "[dry-run] unittest, self_atlas scan, receipt $REC"; fi
