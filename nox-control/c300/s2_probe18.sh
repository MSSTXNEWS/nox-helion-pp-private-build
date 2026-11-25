#!/bin/bash
L=/workspace/nox/svc/logs/whisperlive.log
cat /workspace/nox/svc/whisperlive/run_server.py | head -30
grep -v "connection closed" $L | tail -20 | cut -c1-250
find /workspace/nox -maxdepth 4 -iname "*faster-whisper*" -o -maxdepth 4 -iname "*whisper*" -type d 2>/dev/null | grep -v venv | head
ls /workspace/nox/models 2>/dev/null | head -20
