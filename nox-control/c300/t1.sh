#!/bin/bash
pgrep -af ':8094\|tts' | grep -v grep | cut -c1-200
P=$(ss -ltnp | grep ':8094 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo pid=$P; tr '\0' ' ' </proc/$P/cmdline; echo; ls -l /proc/$P/cwd
tail -15 $(ls -t /root/nox/logs/*tts* 2>/dev/null | head -1) 2>/dev/null | cut -c1-200
grep -n "8094\|/tts\|tts" /root/nox/web_server.py | head -8 | cut -c1-180
curl -s -m5 127.0.0.1:8094/ | head -c 300; echo; curl -s -m5 127.0.0.1:8094/health | head -c 300; echo
