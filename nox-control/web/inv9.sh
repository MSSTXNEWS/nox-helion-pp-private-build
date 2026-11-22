#!/bin/bash
W=/root/nox/web_server.py; df -h /root | tail -1
echo "== web_server markers"; grep -n "Глубокий ответ\|Быстрый слой\|ОСТАНОВЛЕНО\|nox_phase\|NOXFB\|_fast_text\|t1\b\|готовлю в фоне\|\"delta\"\|delta" $W | cut -c1-170 | head -50
echo "== lines/size"; wc -l $W
echo "== gw procs"; for p in 8082 8083 8091 8095; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "$p pid=$pid cwd=$(readlink /proc/$pid/cwd 2>/dev/null) cmd=$(tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | cut -c1-160)"; done
echo "== src"; ls /root/nox/src 2>&1 | head; ls /root/nox/src/wow7 2>&1 | head
echo "== web js markers"; cd /root/nox/web && grep -ln "Глубокий ответ\|готовлю в фоне\|ОСТАНОВЛЕНО\|nox_phase" *.js *.html 2>/dev/null
grep -n "Глубокий ответ\|готовлю в фоне\|ОСТАНОВЛЕНО\|nox_phase" *.js 2>/dev/null | cut -c1-200 | head -12
