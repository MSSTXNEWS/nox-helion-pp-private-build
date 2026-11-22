#!/bin/bash
pgrep -af ":8090\|core_server\|nox_core" | grep -v grep | cut -c1-120
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/cl2.py -o /tmp/cl2.py && python3 /tmp/cl2.py
python3 /root/nox/restart_same.py 8090 2>&1 | tail -1; sleep 4
grep -c "Тортилла" /root/nox/state/core_conv_default.json; curl -s -m3 -o /dev/null -w "core %{http_code}\n" 127.0.0.1:8090/health
