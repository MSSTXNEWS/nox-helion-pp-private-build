N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4w3_files"
echo "S4W3 $(date +%F_%H:%M)"
mkdir -p $N/mods/tests
for f in body_guard restore_full stop_test; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/$f.py || echo "FAIL $f"; done
for f in test_body_guard test_restore_full test_stop_test; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/tests/$f.py || echo "FAIL $f"; done
printf '#!/bin/bash\n# обёртка: перезапуск тела только с cmd, который помещается в VRAM; body_restart.sh не изменён\nexec python3 -I /workspace/nox/mods/body_guard.py "$@"\n' > $N/ops/body_safe_restart.sh; chmod +x $N/ops/body_safe_restart.sh
cd $N/mods && python3 -I -m pytest -q tests/test_body_guard.py tests/test_restore_full.py tests/test_stop_test.py 2>&1 | tail -2
echo "## body_guard --plan (только решение, без перезапуска)"; python3 -I $N/mods/body_guard.py --plan 2>&1 | tail -3 | cut -c1-900
echo "## restore_full"; python3 -I $N/mods/restore_full.py | cut -c1-2500
echo "## stop_test"; python3 -I $N/mods/stop_test.py --trials 2 | cut -c1-1800; echo "rc=$?"
echo "## supervisor restore daemon"
D=/etc/supervisor/conf.d
if [ -d $D ] && [ ! -f $D/nox_restore_full.conf ]; then
cat > $D/nox_restore_full.conf <<CONF
[program:nox_restore_full]
command=nice -n 10 python3 -I /workspace/nox/mods/restore_full.py --daemon
directory=/workspace/nox/mods
autostart=true
autorestart=true
startretries=5
startsecs=3
stopsignal=TERM
stopwaitsecs=10
redirect_stderr=true
stdout_logfile=/workspace/nox/logs/nox_restore_full.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=2
environment=NOX_ROOT="/workspace/nox"
CONF
supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -1; sleep 8
S=$(supervisorctl status nox_restore_full 2>&1 | awk '{print $2}'); echo "status=$S"
[ "$S" = "RUNNING" ] || { echo "ОТКАТ: убираю конфиг"; rm -f $D/nox_restore_full.conf; supervisorctl reread >/dev/null 2>&1; supervisorctl update >/dev/null 2>&1; }
else echo "conf dir missing or conf exists"; fi
