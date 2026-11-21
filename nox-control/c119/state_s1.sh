#!/bin/bash
echo "== redo"; grep -E " OK| BAD|ALL_OK|SOME_BAD" /root/nox/logs/redo.log | cut -c1-90 | tail -12; pgrep -c curl; df -h /dev/shm | tail -1
echo "== server"; pgrep -f "llama-server -m" | head -1; curl -s -m 3 http://127.0.0.1:8081/health; echo; curl -s -m 3 http://127.0.0.1:8082/health; echo
uptime | cut -c1-80
