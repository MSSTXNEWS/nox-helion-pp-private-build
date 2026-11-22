#!/bin/bash
cd /root/nox
ls -la --time-style=full-iso web_server.py* | awk '{print $5,$6,$7,$9}' | tail -6; date
for m in NOXHF NOXHF2 NOXGZ _SG StreamGuard conscience actions "def _chat" NOX_CORE; do echo "$m: $(grep -c "$m" web_server.py)"; done
grep -n "_SG\b\|class _SG\|def _chat" web_server.py | cut -c1-140 | head
echo "== core uses"; for m in conscience actions StreamGuard soul_prime prime_soul LIVING_NOX; do echo "$m: $(grep -c "$m" src/wow7/brain/nox_core.py) / $(grep -rl "$m" repo/nox-control/wow7/brain 2>/dev/null | wc -l)"; done
echo "== soul"; wc -c repo/nox-control/qs6/soul_prompt_ru.txt src/wow7/prime/soul_prime_v3.txt src/wow7/soul_prompt_ru.txt; grep -c LIVING_NOX_V1 repo/nox-control/qs6/soul_prompt_ru.txt src/wow7/soul_prompt_ru.txt; grep -c "приветств" repo/nox-control/qs6/soul_prompt_ru.txt
echo "== core soul src"; grep -n "soul" src/wow7/brain/nox_core.py | cut -c1-160 | head -15
echo "== core env"; pid=$(pgrep -f brain/nox_core.py | head -1); echo pid $pid; tr '\0' '\n' </proc/$pid/environ | grep -E "^NOX_" | cut -c1-90
echo "== diff src vs repo wow7"; diff -rq src/wow7/brain repo/nox-control/wow7/brain 2>&1 | head
ask(){ curl -sN -m150 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$1" | python3 -c "
import sys,json
t=''
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
print(repr(t[:300]))"; }
echo "удали: $(ask '{"messages":[{"role":"user","content":"расскажи про луну"},{"role":"assistant","content":"ок"},{"role":"user","content":"удали прошлые запросы"}],"stream":true}')"
