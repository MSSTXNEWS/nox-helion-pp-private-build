#!/bin/bash
tail -2 /workspace/nox/agent/out/cascade_watchdog.log | cut -c1-100
grep -c "CC_P3" /workspace/nox/web/pkg/server/chat_core.py; pgrep -af web_server.py | head -2 | cut -c1-80; ps -o etimes= -p $(pgrep -f "python web_server.py" | head -1)
sed -i 's/qa-hang-/qa-hang2-/' /workspace/nox/state/p3/hang.py
setsid -f /workspace/nox/venv/bin/python -I /workspace/nox/state/p3/hang.py > /workspace/nox/state/p3/hang2.out 2>&1 < /dev/null
