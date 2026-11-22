#!/bin/bash
echo "== procs:"; for p in 8090 8093 8094 8095 8096 8097 8098 8099; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$pid" ] && echo "$p $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-90)"; done
echo "== mem dir:"; ls /root/nox/memory | head -20 | tr '\n' ' '; echo; ls /root/nox/*.py | xargs -n1 basename | tr '\n' ' '; echo
echo "== s03 grep:"; grep -rl "s03" /root/nox/*.py /root/nox/life 2>/dev/null | head -5
echo "== web_server:"; grep -n "def do_\|def _send\|def _j\|HTTPServer(" /root/nox/web_server.py | head -12; wc -l /root/nox/web_server.py
echo "== start:"; head -8 /root/nox/reload_chat.sh | cut -c1-160; grep -n "web_server" /root/nox/boot_s1.sh | head -3 | cut -c1-200
echo "== tts/stt:"; grep -n "tts\|stt\|8093\|8094\|8095" /root/nox/web_server.py | head -8 | cut -c1-180
echo "== caches:"; du -sh /root/.cache /root/.npm /var/cache/apt /var/lib/apt/lists /var/log /tmp /root/nox/pkg /root/nox/logs /root/nox/canada_dl /root/nox/dl /root/nox/backups /root/nox/memory 2>/dev/null | sort -h | tail -12
du -sh /root/s2_backup* /root/nox/backup_s2 2>/dev/null; ls /root/nox/pkg | head -20 | tr '\n' ' '; echo; df -h /root | tail -1
