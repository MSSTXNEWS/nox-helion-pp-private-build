#!/bin/bash
W=/workspace/nox/web/pkg/server
echo "== chat_core 1-30"; sed -n 1,30p $W/chat_core.py | cut -c1-200
echo "== chat_core 380-460"; sed -n 380,460p $W/chat_core.py | cut -c1-220
echo "== nox_core 1710-1770"; sed -n 1710,1770p /workspace/nox/brain/BRAIN/nox_core.py | cut -c1-220
echo "== web_server _img_generate"; n=$(grep -n "def _img_generate" $W/web_server.py | cut -d: -f1); sed -n "${n},$((n+70))p" $W/web_server.py | cut -c1-220
echo "== grep draw in chat_core/web_server"; grep -n -iE "draw|photo_request|local_generate" $W/chat_core.py $W/web_server.py | cut -c1-200 | head -40
echo "== log dirs"; ls -d /workspace/nox/logs /workspace/nox/log /workspace/nox/state/logs /var/log/supervisor /workspace/logs /tmp/*.log 2>&1 | head; ls /var/log/supervisor 2>/dev/null | head -50
