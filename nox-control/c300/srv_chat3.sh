#!/bin/bash
W=/workspace/nox/web/pkg/server/web_server.py
grep -n "api/turn" $W | head; 
L=$(grep -n "api/turn" $W | head -1 | cut -d: -f1); sed -n "$((L-3)),$((L+45))p" $W | cut -c1-180
echo == test; grep -n "api/turn" -B3 -A12 /workspace/nox/web/pkg/tests/test_chat_unified.py | head -50 | cut -c1-180
