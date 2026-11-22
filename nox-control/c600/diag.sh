#!/bin/bash
echo "== procs"; ps -eo pid,args | grep -E "llama-server|rte_server|nox_core|gateway|web_server" | grep -v grep | cut -c1-400
echo "== files"; find /root /opt /srv -maxdepth 4 \( -name rte_server.py -o -name 'soul_prime*' -o -name gateway_prime.py -o -name nox_core.py -o -name nox_intent.py -o -name FLASH_OPT.json -o -name 'glm_8081.log' -o -name 'start_glm.sh' \) 2>/dev/null | head -30
echo "== FLASH_OPT"; head -c 800 /root/nox/state/FLASH_OPT.json 2>&1
echo "== ctk"; grep -rnE "chat_template_kwargs|enable_thinking|max_tokens|RTE_INTRO|intro" $(find /root /opt -maxdepth 4 \( -name rte_server.py -o -name gateway_prime.py -o -name nox_core.py \) 2>/dev/null) 2>/dev/null | cut -c1-200 | head -40
echo "== glm log"; tail -c 1200 $(find /root -maxdepth 4 -name 'glm_8081.log' | head -1) 2>&1
