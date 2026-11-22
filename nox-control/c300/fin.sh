#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/fin.py -o /tmp/fin.py && python3 /tmp/fin.py
python3 /root/nox/restart_same.py 8091 2>&1 | tail -2
python3 /root/nox/env_restart.py 8082 "NOX_MODEL=быстрый ответ — Qwen3-30B-A3B; глубокий — GLM-5.3-Flash (режим «Глубоко»)" 2>&1 | tail -2
sleep 6; for p in 8091 8082; do echo "$p $(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/)"; done
curl -s -m5 127.0.0.1:8091/api/sys | head -c 400; echo
bash -n /root/nox/boot_s1.sh && echo boot syntax ok
