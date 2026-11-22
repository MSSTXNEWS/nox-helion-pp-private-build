#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/tp.py -o /tmp/tp.py && python3 /tmp/tp.py
python3 /root/nox/restart_same.py 8094 | tail -1; sleep 12
/root/.nox-voice-venv/bin/python /tmp/tt.py 2>&1 | cut -c1-200
