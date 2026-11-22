#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/dm.py -o /tmp/dm.py && python3 /tmp/dm.py
head -12 /root/nox/web_server.py | grep -n "^import\|^from" | cut -c1-150
