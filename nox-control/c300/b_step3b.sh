#!/bin/bash
# b_step3b.sh: чтение маршрутов POST и формата ответа sun_adapter (без генерации)
set -u
W=/workspace/nox
F=$W/ops/sun_adapter/sun_adapter.py
echo "== do_POST routes"; grep -n "def do_POST" -A 30 $F | grep -n "p ==\|p in\|startswith\|path" | head -20
echo "== image handler"; sed -n 386,420p $F
echo "== return shape"; sed -n 420,470p $F | grep -n "return\|send\|json\|image\|\"ok\"\|status" | head -25
echo "== web_server img/generate lines"; sed -n 258,262p $W/web/pkg/server/web_server.py | cut -c1-240
echo "== web_server backup check"; ls -la $W/web/pkg/server/web_server.py*  | tail -5
