#!/bin/bash
cd /root/nox
grep -n "def _log_turn" -A12 web_server.py | cut -c1-220
echo "== keys of last turn"; tail -n1 logs/chat_turns.jsonl | python3 -c "import sys,json; o=json.loads(sys.stdin.read()); print({k:(type(v).__name__, len(str(v))) for k,v in o.items()})"
echo "== _trim_hist / _self_summary / ACTIVE"; grep -n "^def _trim_hist\|^def _self_summary\|^ACTIVE\|^LOCK\|^TAG\|nox_conversation" web_server.py | cut -c1-160
echo "== chat body keys sent by front"; grep -ho "nox_[a-z_]*:" web/nox-chat.js web/nox-newchat.js 2>/dev/null | sort | uniq -c | head
echo "== soul sizes"; wc -c repo/nox-control/qs6/soul_prompt_ru.txt src/wow7/prime/soul_prime_v3.txt; grep -n "^## " src/wow7/prime/soul_prime_v3.txt | cut -c1-70
echo "== env gw has NOX_PROMPT_MAX?"; pid=$(ss -ltnp | grep ":8082 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); tr '\0' '\n' </proc/$pid/environ | grep -c "^NOX_PROMPT_MAX"
echo "== gateway do_POST"; sed -n 65,80p repo/nox-control/glm53/gateway.py | cut -c1-200
