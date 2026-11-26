#!/bin/bash
echo "C300: canon_install7"
N=/workspace/nox; C=$N/canon; S=$N/state/core
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cb=$(date +%s)
curl -fsS -m 30 "$B/bundles/canon/canon.py?cb=$cb" -o $C/canon.py.new && mv $C/canon.py.new $C/canon.py
curl -fsS -m 30 "$B/bundles/canon/sensorium.json?cb=$cb" -o $C/sensorium.json
curl -fsS -m 30 "$B/RUNBOOK_CANON.md?cb=$cb" -o $C/RUNBOOK_CANON.md
PY=$N/venv/bin/python; [ -x $PY ] || PY=python3
df -h /workspace | tail -1 | awk '{print "free",$4}'
echo "--- age"
which age >/dev/null 2>&1 || (DEBIAN_FRONTEND=noninteractive timeout 150 apt-get install -y -qq age >/dev/null 2>&1; true)
echo "age: $(which age || echo none)"
if which age-keygen >/dev/null 2>&1 && [ ! -f $C/age_private.key ]; then
  (umask 077; age-keygen -o $C/age_private.key >/dev/null 2>&1); chmod 600 $C/age_private.key
  age-keygen -y $C/age_private.key > $S/age_pub.txt 2>/dev/null; echo "age key created (pub in state/core/age_pub.txt)"
fi
ls -la $C/age_private.key 2>&1 | awk '{print $1,$5}'
echo "--- sqlite-vec"; timeout 120 $PY -m pip install -q sqlite-vec 2>&1 | tail -1; $PY -I $C/canon.py s03
echo "--- node_exporter"
which prometheus-node-exporter >/dev/null 2>&1 || (DEBIAN_FRONTEND=noninteractive timeout 150 apt-get install -y -qq prometheus-node-exporter >/dev/null 2>&1; true)
NE=$(which prometheus-node-exporter node_exporter 2>/dev/null | head -1); echo "ne: ${NE:-none}"
D=/etc/supervisor/conf.d
if [ -n "$NE" ] && [ -d $D ] && [ ! -f $D/nox_nodeexp.conf ]; then
  printf '[program:nox_nodeexp]\ncommand=%s --web.listen-address=127.0.0.1:9100\nautostart=true\nautorestart=true\n' "$NE" > $D/nox_nodeexp.conf
  supervisorctl reread | tail -1; supervisorctl update | tail -1; sleep 3
fi
curl -s -m 3 127.0.0.1:9100/metrics | grep -c '^node_'
echo "--- drive/selfnow/journal"
$PY -I $C/canon.py drive | grep -E 'encrypted|uploaded|err'
$PY -I $C/canon.py selfnow | $PY -I -c "import sys,json;d=json.load(sys.stdin);print(sorted(d['training'])[:8], sorted(d['telemetry']))"
$PY -I $C/canon.py journal | grep -c ts
supervisorctl restart nox_canon 2>&1 | tail -1
