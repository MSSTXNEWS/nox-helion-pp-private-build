#!/bin/bash
echo "== procs"; ps -eo pid,args | grep -E "llama-server|rte_server|nox_core|gateway|web_server" | grep -v grep | cut -c1-330
echo "== files"; find /root /opt /srv /home -maxdepth 5 \( -name rte_server.py -o -name 'soul_prime*' -o -name 'gateway_prime.py' -o -name nox_core.py -o -name nox_intent.py -o -name FLASH_OPT.json -o -name 'glm_8081.log' -o -name 'start_glm.sh' \) -not -path "*/llama.cpp/*" 2>/dev/null | head -20
echo "== FLASH_OPT"; head -c 600 /root/nox/state/FLASH_OPT.json 2>&1
