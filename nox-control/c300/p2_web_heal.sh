#!/bin/bash
# P2: поднять веб 8091 штатным способом. Бэкап текущего web_server.py; при ошибке синтаксиса откат на .bak_n_ws*. Чат/BRAIN не трогает.
echo "C300: p2_web_heal"; date -u
PY=/workspace/nox/venv/bin/python
WS=$(find /workspace/nox/web -maxdepth 4 -name web_server.py 2>/dev/null | head -1); echo "WS=$WS"
echo "listen before: $(ss -ltnH 'sport = :8091' | wc -l)"
ps -eo pid,etimes,args | grep -E 'web_server|run_server' | grep -v grep | cut -c1-200
if [ -n "$WS" ]; then
  cp -p "$WS" "$WS.bak_p2_$(date -u +%H%M%S)"
  if ! $PY -m py_compile "$WS" 2>/tmp/p2_pyc.err; then
    echo "SYNTAX FAIL:"; head -5 /tmp/p2_pyc.err
    B=$(ls -t "$(dirname $WS)"/web_server.py.bak_n_ws* 2>/dev/null | head -1)
    if [ -n "$B" ] && $PY -m py_compile "$B"; then cp -p "$B" "$WS"; echo "ROLLBACK to $B"; else echo "no valid .bak_n_ws"; fi
  else echo "py_compile OK"; fi
fi
echo "--- logs before restart"; for f in /workspace/nox/agent/out/web_boot.log $(dirname "$WS")/*.log; do [ -f "$f" ] && { echo "== $f $(stat -c %y $f)"; tail -15 "$f" | cut -c1-200; }; done 2>/dev/null
echo "--- start (штатно: run_web.sh)"; bash /workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -8 | cut -c1-200
for i in $(seq 1 12); do ss -ltnH 'sport = :8091' | grep -q . && break; sleep 5; done
echo "listen after: $(ss -ltnpH 'sport = :8091' | cut -c1-120)"
for u in chat.html web/chat.html web/index.html; do echo "GET /$u -> $(curl -s -o /dev/null -m 8 -w '%{http_code}' http://127.0.0.1:8091/$u)"; done
echo "POST /api/chat -> $(curl -s -m 20 -o /tmp/p2_chat.out -w '%{http_code}' -H 'Content-Type: application/json' -d '{"message":"ping","messages":[{"role":"user","content":"ping"}]}' http://127.0.0.1:8091/api/chat) $(head -c 150 /tmp/p2_chat.out | tr '\n' ' ')"
echo "--- logs after"; tail -12 /workspace/nox/agent/out/web_boot.log 2>/dev/null | cut -c1-200
echo "DONE"
