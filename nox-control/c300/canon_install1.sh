#!/bin/bash
echo "C300: canon_install1"
N=/workspace/nox; C=$N/canon; mkdir -p $C/soul
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/canon
cb=$(date +%s)
for f in canon.py sensorium.json; do curl -fsS -m 30 "$B/$f?cb=$cb" -o $C/$f.new && mv $C/$f.new $C/$f; done
ls -la $C | head
PY=$N/venv/bin/python; [ -x $PY ] || PY=python3
for c in passport birth backup selfnow morning evening exam verify disk; do echo "--- $c"; $PY -I $C/canon.py $c 2>&1 | head -40 | cut -c1-220; done
echo "--- feelings"; $PY -I $C/canon.py feelings | head -30
echo "--- supervisor conf dir"; ls -d /etc/supervisor/conf.d 2>&1; ls /etc/supervisor/conf.d 2>/dev/null | head -5
D=/etc/supervisor/conf.d
if [ -d $D ] && [ ! -f $D/nox_canon.conf ]; then
cat > $D/nox_canon.conf <<CONF
[program:nox_canon]
command=$PY -I $C/canon.py daemon
directory=$C
autostart=true
autorestart=true
startsecs=3
priority=900
stdout_logfile=$C/daemon.out
stderr_logfile=$C/daemon.err
CONF
supervisorctl reread 2>&1 | tail -2; supervisorctl update 2>&1 | tail -2
fi
sleep 3; supervisorctl status nox_canon 2>&1 | head -2
