echo "K1: l2_mem_sup1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
cat /etc/supervisor/conf.d/nox_guard_svc.conf | head -15
cat > /etc/supervisor/conf.d/nox_mem.conf <<CF
[program:nox_mem]
command=$N/venv_mem/bin/python $N/svc/mem/nox_mem.py
directory=$N/svc/mem
autostart=true
autorestart=true
startsecs=3
stdout_logfile=$N/svc/logs/mem.log
stderr_logfile=$N/svc/logs/mem.log
stopasgroup=true
killasgroup=true

[program:nox_rerank]
command=$N/venv/bin/python $N/svc/mem/nox_rerank.py
directory=$N/svc/mem
autostart=true
autorestart=true
startsecs=10
stdout_logfile=$N/svc/logs/rerank.log
stderr_logfile=$N/svc/logs/rerank.log
stopasgroup=true
killasgroup=true
CF
pkill -f svc/mem/nox_mem.py; pkill -f svc/mem/nox_rerank.py; sleep 2
supervisorctl reread 2>&1 | tail -3; supervisorctl update 2>&1 | tail -3
for i in $(seq 1 30); do curl -s -m 2 127.0.0.1:8083/ >/dev/null && curl -s -m 2 127.0.0.1:18220/health && break; sleep 3; done; echo
supervisorctl status nox_mem nox_rerank 2>&1 | head
python3 - <<'PY'
import sqlite3,json,urllib.request as ur
c=sqlite3.connect("/workspace/nox/state/living/mem.db")
for n,sql in c.execute("select name,sql from sqlite_master where type='table'"): print("tbl",n,(sql or "")[:200].replace("\n"," "))
PY
