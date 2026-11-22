#!/bin/bash
W=/root/nox/web_server.py
echo "== web_server 255-321"; sed -n 255,321p $W | cut -c1-230
G=/root/nox/repo/nox-control/glm53; ls $G | head -30; wc -l $G/gateway.py
echo "== gw grep"; grep -n "system\|soul\|persona\|8083\|fast\|state\|telemetry\|телеметр\|nox_mode\|def " $G/gateway.py | cut -c1-160 | head -90
