#!/bin/bash
echo "C300: canon_install5"
N=/workspace/nox; C=$N/canon
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/canon
cb=$(date +%s); curl -fsS -m 30 "$B/canon.py?cb=$cb" -o $C/canon.py.new && mv $C/canon.py.new $C/canon.py
PY=$N/venv/bin/python; [ -x $PY ] || PY=python3
echo "--- drive"; $PY -I $C/canon.py drive
supervisorctl restart nox_canon 2>&1 | tail -1; sleep 3; supervisorctl status nox_canon | head -1
