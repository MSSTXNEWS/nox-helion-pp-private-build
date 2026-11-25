#!/bin/bash
cd /workspace/nox/tools
pkill -f "s2_feeds.py loop"; sleep 1
(nohup setsid python3 s2_feeds.py catalog > /workspace/nox/svc/logs/s2_cat.log 2>&1 < /dev/null &)
for i in $(seq 1 24); do sleep 10; pgrep -f "s2_feeds.py catalog" >/dev/null || break; done
cat /workspace/nox/svc/logs/s2_cat.log | cut -c1-900
(nohup setsid python3 /workspace/nox/tools/s2_feeds.py loop >> /workspace/nox/svc/logs/s2_feeds.log 2>&1 < /dev/null &)
sleep 2; pgrep -fa s2_feeds | head; ls -la /workspace/nox/web/site/data/cinema_catalog.json
