#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-170; }
echo "== sv"; supervisorctl status | awk '{print $1,$2,$4,$5,$6}' | a
echo "== gpu"; nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader
echo "== web"; ls /opt/nox-web 2>&1 | head -30 | tr '\n' ' '; echo; ls /opt/nox-web/nox-v14* 2>&1 | tr '\n' ' '; echo
echo "== train confs"; grep -l -iE "train|lora|distill|learn|forge" /etc/supervisor/conf.d/*.conf | a
for C in $(grep -l -iE "train|lora|distill|learn" /etc/supervisor/conf.d/*.conf); do grep -E "^\[program|^command=|^autostart" $C | a; done
echo "== state"; ls -t /root/nox/state | head -20 | tr '\n' ' '; echo
echo "== llm"; grep -E "^\[program|^command" /etc/supervisor/conf.d/nox-ds41-8098.conf | a; curl -s -m5 127.0.0.1:8098/health; echo
df -h / | tail -1; free -g | head -2
