#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-240; }
echo "== dispatcher status"; head -c 700 /root/nox/status/dispatcher_t855u.json | a; echo
echo "== agents"; head -c 900 /root/nox/status/agents_t856u.json | a; echo
echo "== dispatcher log"; ls /root/nox/logs | grep -i dispatcher | head -3; tail -n 8 /root/nox/logs/nox_dispatcher_t855u.log 2>/dev/null | a
python3 - <<'PY'
import json,collections
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks']
p=[(k,t) for k,t in s.items() if t.get('status')=='pending']
print('pending',len(p)); 
for k,t in p[:3]: print(k,{x:t.get(x) for x in ('class','lane','deps','locks','handler','assigned_to','next_try','retries')})
b=[(k,t) for k,t in s.items() if t.get('status')=='blocked']
for k,t in b[:3]: print('blocked',k,{x:str(t.get(x))[:90] for x in ('handler','deps','locks','note','result','last_error')})
PY
