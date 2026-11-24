#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/nox-dock-wow.js -o /workspace/nox/web/site/nox-dock-wow.js && echo "dock js $(wc -c < /workspace/nox/web/site/nox-dock-wow.js)"
curl -fsSL $R/dk.py -o /tmp/dk.py && /workspace/nox/venv/bin/python /tmp/dk.py
tail -3 /workspace/nox/agent/out/c300_pw.log; tail -25 /workspace/nox/agent/out/c300_bt.log
