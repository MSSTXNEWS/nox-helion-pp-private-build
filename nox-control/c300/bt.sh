#!/bin/bash
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright; print('pw ok')" 2>&1 | tail -1
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bt.py -o /tmp/bt.py && timeout 280 $PY /tmp/bt.py 2>&1 | tail -30
