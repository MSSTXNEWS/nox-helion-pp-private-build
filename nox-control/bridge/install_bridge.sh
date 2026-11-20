#!/bin/bash
set -e
mkdir -p /opt/nox-bridge
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/bridge/nox_bridge.py -o /opt/nox-bridge/nox_bridge.py
cat > /etc/supervisor/conf.d/nox-bridge.conf <<'EOF'
[program:nox-bridge]
command=/root/nox/venv/bin/python -u /opt/nox-bridge/nox_bridge.py
directory=/root/nox
autostart=true
autorestart=true
startsecs=5
stdout_logfile=/root/nox/logs/nox_bridge.out.log
stderr_logfile=/root/nox/logs/nox_bridge.err.log
stdout_logfile_maxbytes=5MB
stderr_logfile_maxbytes=5MB
EOF
supervisorctl reread >/dev/null; supervisorctl update >/dev/null
supervisorctl restart nox-bridge >/dev/null 2>&1 || true
sleep 8
supervisorctl status nox-bridge
curl -s -m 5 http://127.0.0.1:8091/health; echo
/root/nox/venv/bin/python - <<'PY'
import json, urllib.request
q = {"messages": [{"role": "user", "content": "Привет! Кто ты и что ты помнишь про свой проект? Ответь коротко."}], "max_tokens": 900}
req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/completions", data=json.dumps(q).encode(), headers={"Content-Type": "application/json"})
try:
    r = json.loads(urllib.request.urlopen(req, timeout=175).read())
    print("NOX:", r["choices"][0]["message"]["content"][:500], "| memory_used:", r.get("memory_used"))
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:200])
PY
tail -3 /root/nox/logs/nox_bridge.log 2>/dev/null | cut -c1-200 || true
