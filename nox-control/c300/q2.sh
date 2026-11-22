#!/bin/bash
echo "== changed last 90 min"; find /root/nox/web /root/nox/web_server.py /root/nox/repo/nox-control/wow7 /root/nox/repo/nox-control/glm53 /root/nox/start_glm.sh -mmin -90 -type f 2>/dev/null | grep -v __pycache__ | head -20
echo "== who serves 8091"; pgrep -af "8091\|web_server\|rte_server" | cut -c1-140
grep -n "rte\|8084" /root/nox/web_server.py | head -5 | cut -c1-160
grep -o 'src="[^"]*"' /root/nox/web/chat.html | tr '\n' ' ' | cut -c1-900
