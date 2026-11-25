#!/bin/bash
# P3 recon1: read-only. draw module + chat_core signatures + logs for ImportError.
echo "== draw dir"; ls -la /workspace/nox/ops/draw 2>&1 | head; 
echo "== invoke_draw.py"; cat /workspace/nox/ops/draw/invoke_draw.py 2>&1 | head -60
echo "== grep refs"
grep -rIn --include=*.py -E "invoke_draw|draw_request|ops\.draw|ops/draw" /workspace/nox --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=backup 2>/dev/null | cut -c1-220 | head -40
echo "== /img/generate refs"
grep -rIn --include=*.py --include=*.html -E "/img/generate" /workspace/nox 2>/dev/null | cut -c1-200 | head -15
echo "== listeners"; (ss -ltnp 2>/dev/null || netstat -ltnp) | awk '{print $4, $6, $7}' | head -40
echo "== logs ImportError/FileNotFound"
for f in $(ls -t /workspace/nox/logs/*.log /workspace/nox/log/*.log /var/log/supervisor/*.log 2>/dev/null | head -60); do
  n=$(tail -n 3000 "$f" 2>/dev/null | grep -cE "ImportError|ModuleNotFoundError|FileNotFoundError|No such file"); [ "$n" -gt 0 ] && { echo "-- $f $n"; tail -n 3000 "$f" | grep -E "ImportError|ModuleNotFoundError|FileNotFoundError|No such file" | sort | uniq -c | sort -rn | cut -c1-240 | head -4; }
done
