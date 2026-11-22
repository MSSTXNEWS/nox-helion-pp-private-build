#!/bin/bash
cd /root/nox
echo "== v7 dirs"; ls /root/nox/dl/v7 /root/nox/src/wow7 /tmp/nox_v7 2>&1 | head -40
echo "== receipts"; ls -t /root/nox/receipts /root/nox/state/receipts /root/nox/logs 2>/dev/null | head -40
find / -xdev \( -name "S1_0*" -o -name "*S1_0*receipt*" \) -mmin -600 2>/dev/null | head -30
echo "== web_server markers"; for m in NOXHF NOXHF2 NOX_CORE StreamGuard conscience _SG actions; do echo "$m: $(grep -c "$m" web_server.py)"; done
ls -la web_server.py* | head; ls /root/nox/.soul_merged_hotfix2 2>&1
echo "== ports"; ss -ltn | grep -E ":(8081|8082|8083|8091|8190|8092) " | awk '{print $4}'
for p in chat.html resonance.html index.html; do echo "$p $(curl -s -m6 -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p)"; done
echo "== v7 services"; ps aux | grep -E "nox_core|nox_wow|wow7|watch|dispatcher" | grep -v grep | awk '{print $11,$12,$13}' | head
echo "== gateway env flags"; pid=$(ss -ltnp | grep ":8082 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); tr '\0' '\n' </proc/$pid/environ | grep -E "^NOX_(CORE|CONSC|FAST|MODEL)" | cut -c1-80
echo "== v7 deploy log tail"; ls -t /root/nox/logs | head -15; tail -n 25 /root/nox/logs/v7*.log 2>/dev/null | cut -c1-200
echo "== HANDOFF"; ls /root/nox/dl/v7/v4/nox_wow/DEPLOY 2>/dev/null
