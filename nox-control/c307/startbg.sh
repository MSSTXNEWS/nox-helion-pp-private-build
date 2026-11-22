#!/bin/bash
pkill -f flash_start.sh; pkill -f "llama-server.*--port 8081"; sleep 2
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c307/start.sh -o /root/nox/flash_start.sh
nohup setsid bash /root/nox/flash_start.sh > /root/nox/logs/flash_start.log 2>&1 < /dev/null &
echo started
