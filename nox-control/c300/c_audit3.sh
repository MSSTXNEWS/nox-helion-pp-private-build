#!/bin/bash
# c_audit3: read-only детали провалов ревизора по пунктам
W=/workspace/nox/web/site/qa
python3 -I -c "
import json
d=json.load(open('$W/audit.json'))
for k in ('chat','index','consciousness'):
  v=d.get(k,{})
  for n,x in sorted(v.get('items',{}).items(), key=lambda t:int(t[0])):
    if x.get('status')=='rework': print(k, n, x.get('detail','')[:160])
" 2>&1 | head -c 4000
echo "NINJA IN PAGES:"; grep -l 'nox-ninja' /workspace/nox/web/site/chat.html /workspace/nox/web/site/index.html /workspace/nox/web/site/consciousness.html 2>&1
