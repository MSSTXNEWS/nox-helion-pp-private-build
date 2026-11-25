#!/bin/bash
S=/workspace/nox/web/site
echo "== GL2"; ls -la /workspace/nox/svc/glance | head; ls /workspace/nox/svc/data | head -20
ss -ltn | awk '{print $4}' | grep -o ':[0-9]*$' | sort -u | tr '\n' ' '; echo
echo "-- svc pages"; grep -l "/svc/" $S/*.html | head; 
f=$(grep -l "/svc/filebrowser" $S/*.html | head -1); echo F=$f; wc -c $f; grep -n "iframe" $f | cut -c1-300 | head -5
echo "-- core"; ps -eo pid,args | grep -i "nox_core\|liska\|uvicorn\|glm" | grep -v grep | cut -c1-200 | head
echo "-- state"; ls /workspace/nox/state | head -30
echo "-- svc_registry keys"; /workspace/nox/venv/bin/python -c "import json;print(list(json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'))))"
echo "-- persona in live core"; for f in /workspace/nox/tmp/liska_alive/nox_core.py; do grep -n "persona\|state/" $f | cut -c1-160 | head -8; done
echo "-- settings personality"; grep -n "personality" $S/nox-settings-tabs.js | cut -c1-260 | head -8
