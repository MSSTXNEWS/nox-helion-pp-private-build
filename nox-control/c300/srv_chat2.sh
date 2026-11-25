#!/bin/bash
N=/workspace/nox
grep -rln "api/turn" $N --include=*.py --include=*.js 2>/dev/null | head -8
echo ==; grep -rn "api/turn" $N/web_server.py $N/brain 2>/dev/null --include=*.py | cut -c1-220 | head -8
echo == watcher; cat $N/state/p3/restart_watch.log | tail -8; pgrep -af restart_watch | head -2
echo == chat_hold; stat -c %Y $N/state/orch/chat_hold; date +%s
