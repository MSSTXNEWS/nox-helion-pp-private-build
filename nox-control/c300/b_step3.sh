#!/bin/bash
# b_step3.sh: чтение контракта sun_adapter :8097, функции _proxy и фронтовых вызовов генерации (без запуска генерации)
set -u
W=/workspace/nox
S=$W/web/site
echo "== sun_adapter source"
F=$(grep -rl "sun_adapter" $W --include=*.py 2>/dev/null | grep -v venv | head -8); echo "$F"
for f in $F; do echo "-- $f"; grep -n "def do_POST\|def do_GET\|/generate\|/health\|\"prompt\"\|'prompt'\|\"brief\"\|\"slider\"\|\"steps\"\|\"width\"\|\"size\"" "$f" | head -20; done
echo "== _proxy in web_server.py"
grep -n "def _proxy" -A 14 $W/web/pkg/server/web_server.py | head -30
echo "== frontend callers of img/generate"
grep -rln "img/generate" $S --include=*.html --include=*.js 2>/dev/null | head -10
grep -rn "img/generate" $S --include=*.js --include=*.html 2>/dev/null | head -8 | cut -c1-260
echo "== sun_adapter live state"
curl -s --max-time 5 http://127.0.0.1:8097/health | head -c 400; echo
