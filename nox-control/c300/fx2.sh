#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/fx2.py -o /tmp/fx2.py && python3 /tmp/fx2.py
grep -h "deep-mem\|автозапись\|memory" /root/nox/logs/web_server.log /root/nox/logs/gateway.log | tail -6 | cut -c1-200
ls /root/nox/repo/nox-control/wow7 | head -30 | tr '\n' ' '; echo; find /root/nox -name 'affect_loop.py' -o -name 'nox_workspace.py' 2>/dev/null | head
