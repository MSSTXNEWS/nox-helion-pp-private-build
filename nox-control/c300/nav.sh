#!/bin/bash
grep -o '.\{0,200\}cinema.html.\{0,120\}' /workspace/nox/web/site/nav.json | head -2
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/nav.py -o /tmp/nav.py && python3 /tmp/nav.py
grep -o '.\{0,120\}tools.html.\{0,80\}' /workspace/nox/web/site/nav.json | head -2
cat /workspace/nox/agent/out/c300_libs.log | tail -40
