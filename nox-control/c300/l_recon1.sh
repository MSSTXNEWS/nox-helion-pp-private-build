cd /workspace/nox
echo "== persona"; python3 - <<'P'
import json;d=json.load(open('/workspace/nox/state/persona.json'));print(list(d.keys()))
for k,v in d.items(): print(k, str(v)[:600].replace('\n',' '))
P
echo "== living"; ls state/living 2>&1 | head
echo "== chat_core"; wc -l web/pkg/server/chat_core.py; grep -n "persona\|system_hint\|living\|def " web/pkg/server/chat_core.py | head -80
echo "== site chat js"; ls web/site | grep -i "nox-chat\|nox-l-\|nox-fx\|nox-first\|proact" 
echo "== registry"; python3 - <<'P'
import json;r=json.load(open('/workspace/nox/web/site/qa/registry.json'));print(type(r),len(r))
it=r if isinstance(r,list) else r.get('commands',r.get('items',list(r.items())))
print(str(it)[:3000])
P
echo "== features"; ls state | head -60; df -h /workspace | tail -1
