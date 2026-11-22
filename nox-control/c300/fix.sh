#!/bin/bash
pkill -9 -f 'llama-server.*--port 8081'; sleep 3; pgrep -f 'port 8081' || echo freed
sed -i 's/^pkill.*/pkill -9 -f "llama-server.*--port 8081"; sleep 3/' /root/nox/start_glm.sh
nohup setsid bash /root/nox/flash_ab.sh >/dev/null 2>&1 < /dev/null &
echo restarted
