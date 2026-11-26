#!/bin/bash
echo "C300: canon_install4"
N=/workspace/nox; C=$N/canon
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/canon
cb=$(date +%s); curl -fsS -m 30 "$B/canon.py?cb=$cb" -o $C/canon.py.new && mv $C/canon.py.new $C/canon.py
PY=$N/venv/bin/python; [ -x $PY ] || PY=python3
F=$N/agent/nox_agents/sleep.py
if grep -q 'return 1 <= h < 7' $F; then cp -n $F $F.bak_canon_20261126; sed -i 's/return 1 <= h < 7/return 2 <= h < 5  # canon v5 ch5: sleep 02:00-05:00 MSK/' $F; echo "sleep window patched"; fi
grep -n 'return . <= h < .' $F
echo "--- morning (redacted)"; $PY -I $C/canon.py morning | $PY -I -c "import sys,json;d=json.load(sys.stdin);print('lines',len(d['lines']),'dream_is_HOLD',d['lines'][0].startswith('Снилось: HOLD'),'dream_len',len(d['lines'][0]))"
echo "--- unknown (counts only)"; $PY -I $C/canon.py unknown
echo "--- hunger"; $PY -I $C/canon.py hunger | grep -E 'level|hours'
echo "--- backup"; $PY -I $C/canon.py backup | grep -E 'restore_ok|bytes|files'
supervisorctl restart nox_canon 2>&1 | tail -1; sleep 3; supervisorctl status nox_canon | head -1
