#!/bin/bash
# c_audit2: read-only состояние ревизора и статусы по пунктам чек-листа
N=/workspace/nox; W=$N/web/site/qa
echo "RUNNING:"; pgrep -af qa_audit.py | head -3
echo "LOG TAIL:"; tail -c 1500 $N/state/c_audit1.log 2>/dev/null
echo "AUDIT STATUS:"; python3 -I -c "
import json
d=json.load(open('$W/audit.json'))
for k in ('chat','index','consciousness','organism'):
  v=d.get(k,{})
  print(k, v.get('ts'), v.get('status'), 'WOW', v.get('wow'), 'ARU', v.get('ARU'))
  it=v.get('items',{})
  print('  ', {n:x.get('status') for n,x in sorted(it.items(), key=lambda t:int(t[0]))})
" 2>&1 | head -c 3000
