#!/bin/bash
cp /root/nox/start_glm.sh /root/nox/start_glm.sh.ab3best; rm -f /root/nox/logs/flash_ab4.log
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/ab4.py -o /root/nox/flash_ab4.py
nohup setsid python3 /root/nox/flash_ab4.py >/dev/null 2>&1 </dev/null & echo started
