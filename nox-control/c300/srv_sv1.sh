#!/bin/bash
C=/etc/supervisor/conf.d/nox_cascade.conf; N=/workspace/nox
cat > $C <<'EOF'
[program:nox_cascade]
command=/bin/bash -c 'set -a; [ -f /workspace/nox/secrets.env ] && . /workspace/nox/secrets.env; set +a; exec /workspace/nox/venv/bin/python -m cascade'
directory=/workspace/nox
environment=NOX_VOL="/workspace",NOX_BRAIN_DIR="/workspace/nox/brain",NOX_CASCADE_PORT="8400",PYTHONUNBUFFERED="1"
autostart=true
autorestart=true
startsecs=5
startretries=20
priority=220
stdout_logfile=/workspace/nox/agent/out/cascade_8400.log
stderr_logfile=/workspace/nox/agent/out/cascade_8400.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=2
stopasgroup=true
killasgroup=true
EOF
echo "old: wd=$(pgrep -f cascade_watchdog.sh) casc=$(pgrep -f 'python -m cascade')"
kill $(pgrep -f cascade_watchdog.sh) 2>/dev/null; sleep 1; kill $(pgrep -f 'python -m cascade') 2>/dev/null; sleep 2
supervisorctl reread 2>&1 | tail -2; supervisorctl update 2>&1 | tail -2
ok=0; for i in $(seq 1 10); do sleep 3; curl -fs -m2 127.0.0.1:8400/health >/dev/null && { ok=1; echo "up after $((i*3))s"; break; }; done
supervisorctl status nox_cascade
if [ $ok = 0 ]; then echo ROLLBACK; supervisorctl stop nox_cascade; rm -f $C; supervisorctl update; setsid -f bash $N/agent/cascade_watchdog.sh > /dev/null 2>&1 < /dev/null; sleep 8; curl -s -m3 127.0.0.1:8400/health; fi
echo "$(date -u +%FT%TZ) SRV: cascade под supervisord (nox_cascade), watchdog остановлен; откат: rm $C; supervisorctl update; setsid -f bash $N/agent/cascade_watchdog.sh" >> $N/state/p3/ledger_srv.txt
sleep 15; curl -s -m3 127.0.0.1:8400/health; echo; tail -3 $N/agent/out/cascade_8400.log | cut -c1-120
