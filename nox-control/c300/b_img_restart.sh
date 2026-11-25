#!/bin/bash
# b_img_restart.sh: перезапуск web_server.py с тем же окружением/cwd/логом; проверка порта; один тест /img/generate (512px, 8 шагов)
set -u
W=/workspace/nox
PID=$(pgrep -f "web_server.py" | head -1)
CWD=$(readlink /proc/$PID/cwd); LOG=$(readlink /proc/$PID/fd/1); PORT_LINE=$(ss -ltnp 2>/dev/null | grep "pid=$PID," | head -1)
echo "old pid=$PID cwd=$CWD log=$LOG"; echo "listen: $PORT_LINE"
cp /proc/$PID/environ /tmp/ws_env.bin
kill -TERM $PID; for i in $(seq 1 20); do kill -0 $PID 2>/dev/null || break; sleep 1; done
python3 - "$CWD" "$LOG" <<'PY'
import sys, subprocess
cwd, log = sys.argv[1], sys.argv[2]
raw = open('/tmp/ws_env.bin','rb').read().decode('utf-8','replace').split('\0')
env = dict(x.split('=',1) for x in raw if '=' in x)
subprocess.Popen(['/workspace/nox/venv/bin/python','web_server.py'], cwd=cwd, env=env, stdout=open(log,'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
print("started")
PY
sleep 6
NEW=$(pgrep -f "web_server.py" | head -1); echo "new pid=$NEW"
ss -ltnp 2>/dev/null | grep "pid=$NEW," | head -2
PORT=$(ss -ltnp 2>/dev/null | grep "pid=$NEW," | head -1 | sed -E 's/.*:([0-9]+) .*/\1/')
echo "port=$PORT"
echo "== /img/health"; curl -s --max-time 10 http://127.0.0.1:$PORT/img/health | head -c 300; echo
echo "== one generate (512px, 8 steps)"
curl -s -o /tmp/b_img_test.json -w "%{http_code}\n" --max-time 600 -X POST http://127.0.0.1:$PORT/img/generate -H 'Content-Type: application/json' -d '{"prompt":"тестовая карточка, тёмное стекло, чёрный фон","width":512,"height":512,"steps":8,"seed":42}'
head -c 500 /tmp/b_img_test.json; echo
grep -n "img_generate\|8097" "$CWD/web_server.py" 2>/dev/null | head -3
