#!/bin/bash
F=$(find /root /opt /srv -maxdepth 5 \( -name rte_server.py -o -name gateway_prime.py -o -name nox_core.py \) -not -path "*/llama.cpp/*" 2>/dev/null)
echo "$F"
grep -nE "chat_template_kwargs|enable_thinking|max_tokens|RTE_INTRO|intro|tier|fallback" $F 2>/dev/null | cut -c1-170 | head -45
