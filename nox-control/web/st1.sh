#!/bin/bash
cd /root/nox
for f in receipts/V7-*.json; do echo "== $f"; python3 -c "
import json,sys; o=json.load(open('$f')); print({k:(v if len(str(v))<120 else str(v)[:120]) for k,v in o.items()})"; done
echo "== web_server _chat"; sed -n 73,140p web_server.py | cut -c1-210
echo "== gateway: soul/core hooks"; grep -n "NOX_CORE\|soul\|conscience\|StreamGuard\|actions" repo/nox-control/glm53/gateway.py repo/nox-control/qs6/*.py 2>/dev/null | cut -c1-170 | head -40
echo "== ask"; ask(){ curl -sN -m120 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$1" | python3 -c "
import sys,json
t=''
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
print(repr(t[:300]))"; }
for i in 1 2 3; do echo "привет#$i: $(ask '{"messages":[{"role":"user","content":"привет"}],"stream":true}')"; done
echo "сервер: $(ask '{"messages":[{"role":"user","content":"как сервер?"}],"stream":true}')"
