#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control
for f in nox-newchat.js nox-newchat.css; do T=$(find /root/nox/web -maxdepth 2 -name $f | head -1); [ -n "$T" ] && curl -fsSL $R/c137/$f -o $T && echo "patched $T"; done
curl -fsSL $R/c122/boot_s1.sh -o /root/nox/boot_s1.sh; chmod +x /root/nox/boot_s1.sh
M='быстрый ответ — Qwen3.5-9B; глубокий — GLM-5.3 (отвечает только когда загружен)'
sed -i "s|^export NOX_MODEL=.*|export NOX_MODEL=\"$M\"|" /root/nox/boot_s1.sh
# перезапуск только шлюза с новым NOX_MODEL
pkill -f "python3 .*gateway.py"; sleep 1; NOX_MODEL_RESTART=1 bash /root/nox/boot_s1.sh 2>&1 | tail -12
curl -s -m 60 http://127.0.0.1:8091/api/chat -d '{"model":"nox-helion:latest","stream":false,"messages":[{"role":"user","content":"на каком ядре ты сейчас отвечаешь и как меня зовут?"}]}' | head -c 700
