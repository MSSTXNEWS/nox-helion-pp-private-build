echo "C300: srv_k75"
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner; N=/workspace/nox
curl -s -m 30 "$R/owner_active.py?cb=$cb" -o $N/stewards/owner_active.py; curl -s -m 30 "$R/patch_draw.py?cb=$cb" -o /tmp/patch_draw_k1.py
wc -l $N/stewards/owner_active.py /tmp/patch_draw_k1.py | tail -3
cp $N/ops/draw/invoke_draw.py $N/ops/draw/invoke_draw.py.bak_k1_hold_$(date +%s)
$N/venv/bin/python -I /tmp/patch_draw_k1.py && echo PATCHED; $N/venv/bin/python -I -m py_compile $N/ops/draw/invoke_draw.py && echo DRAW_OK
echo 0 > $N/state/draw_hold_s
cat > /etc/supervisor/conf.d/nox_owner_active.conf <<'C'
[program:nox_owner_active]
command=/workspace/nox/venv/bin/python -u /workspace/nox/stewards/owner_active.py
directory=/workspace/nox
autostart=true
autorestart=true
startsecs=5
stopsignal=TERM
stopwaitsecs=10
stdout_logfile=/workspace/nox/state/orch/owner_active.stdout
stderr_logfile=/workspace/nox/state/orch/owner_active.stdout
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=1
C
$N/venv/bin/python -I -m py_compile $N/stewards/owner_active.py && supervisorctl update 2>&1 | tail -2
sleep 8; supervisorctl status nox_owner_active; cat $N/state/orch/owner_active.log | tail -5; cat $N/state/orch/owner_active.stdout | tail -5
