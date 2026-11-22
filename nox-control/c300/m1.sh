#!/bin/bash
W=/root/nox/web_server.py; C=/root/nox/repo/nox-control/glm53
echo "== deep block"; grep -n "_deep\|NOX_DEEP_DIRECT\|_B = \|soul\|recall\|8095\|memory" $W | head -30 | cut -c1-150
echo "== gw recall"; grep -n "8095\|RECALL\|def .*recall\|/recall\|/search" $C/gateway.py $C/qs6_core.py 2>/dev/null | head -15 | cut -c1-160
echo "== recall svc"; pgrep -af ':8095\|recall' | cut -c1-150; curl -s -m3 127.0.0.1:8095/ | head -c 300; echo
