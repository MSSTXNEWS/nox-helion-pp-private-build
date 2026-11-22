#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/w2.py -o /tmp/w2.py && python3 /tmp/w2.py && python3 /root/nox/restart_same.py 8091 | tail -1
pgrep -f mtp_ab.sh >/dev/null && echo "mtp running"; cat /root/nox/logs/mtp_ab.log
