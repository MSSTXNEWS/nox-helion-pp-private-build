#!/bin/bash
# b_drive_probe.sh: только чтение: мост Google Диска :18765, маршрут /drive в web_server, свободное место, наличие пакетов кинотеатра
set -u
W=/workspace/nox
echo "== disk"; df -h $W | tail -1
echo "== bridge 18765"
for p in / /health /files /list /api/files; do printf "%s -> " $p; curl -s -o /tmp/b_br.txt -w "%{http_code} " --max-time 5 http://127.0.0.1:18765$p; head -c 160 /tmp/b_br.txt; echo; done
echo "== web_server /drive route"; grep -n '"/drive' $W/web/pkg/server/web_server.py | head -3 | cut -c1-220
echo "== existing cinema pkg dir"; ls -la $W/web/site/vendor/cinema_pkg 2>/dev/null || echo "no cinema_pkg"
echo "== bridge source"; grep -rl "18765" $W --include=*.py 2>/dev/null | grep -v venv | head -5
