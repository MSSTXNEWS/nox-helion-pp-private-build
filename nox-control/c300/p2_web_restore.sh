#!/bin/bash
echo "C300: p2_web_restore"; N=/workspace/nox; B=$N/backup; PY=$N/venv/bin/python
echo "## search backups for ops/draw"; FOUND=""
for t in $(ls -t $B/nox_cfg_*.tgz 2>/dev/null); do echo "-- $t"; tar -tzf "$t" 2>/dev/null | grep -E 'ops/draw/|invoke_draw' | head -8; if tar -tzf "$t" 2>/dev/null | grep -q 'ops/draw/invoke_draw.py'; then FOUND=$t; break; fi; done
if [ -z "$FOUND" ]; then for d in $B/nox-backup-20261125-0030 $B/nox-backup-20261124-0030 $B/web_20261123_025249; do echo "-- dir $d"; ls $d | head -12; find $d -name 'invoke_draw*' 2>/dev/null | head -3; done; fi
echo "-- nox_mem tgz list grep (first hit only)"; [ -z "$FOUND" ] && timeout 150 tar -tzf $B/nox_mem_20261125_031701.tgz 2>/dev/null | grep -m3 'invoke_draw'
echo "-- restic repo (list only)"; ls $B/restic | head
echo "FOUND=$FOUND"
if [ -n "$FOUND" ]; then
  T=/tmp/p2_draw_restore; rm -rf $T; mkdir -p $T; tar -xzf "$FOUND" -C $T --wildcards '*ops/draw/*' 2>&1 | tail -2
  SRC=$(find $T -type d -path '*ops/draw' | head -1); echo "SRC=$SRC"; ls -la "$SRC" | head -20
  if [ -f "$SRC/invoke_draw.py" ] && $PY -m py_compile "$SRC/invoke_draw.py"; then
    [ -e $N/ops/draw ] && { echo "ops/draw already exists, abort"; exit 1; }
    cp -a "$SRC" $N/ops/draw && echo "RESTORED ops/draw from $FOUND (backup file date: $(stat -c %y $FOUND))"
    (cd $N/web/pkg/server && $PY -c "import chat_core; print('chat_core import OK')" 2>&1 | tail -3)
    bash $N/web/pkg/server/run_web.sh restart 2>&1 | tail -4 | cut -c1-200
    for u in chat.html web/chat.html web/index.html api/chat/health; do echo "GET /$u -> $(curl -s -o /dev/null -m 8 -w '%{http_code}' http://127.0.0.1:8091/$u)"; done
  else echo "restored file invalid"; fi
fi
echo "DONE"
