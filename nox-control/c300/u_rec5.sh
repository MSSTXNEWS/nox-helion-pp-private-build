echo "C300: u_rec5"
S=/workspace/nox/web/site; cd $S
python3 - <<'PYX'
import json
r=json.load(open('qa/registry.json',encoding='utf-8'))
for i,c in enumerate(r['checklist'],1):
    if i in (3,4,9,23) or 'id' in c and str(c['id']) in ('3','4','9','23'): print('CHK',i,c)
print('n',len(r['checklist']))
a=json.load(open('qa/audit.json',encoding='utf-8'))
print(type(a).__name__,list(a)[:6] if isinstance(a,dict) else '')
PYX
ls -la qa/ | head -20; for p in creative settings; do echo "-- $p"; ls qa/rework | grep "^$p"; tail -c 1800 qa/rework/$p.rework 2>/dev/null; done
cat /workspace/nox/agent/out/u_qaa_prog.txt
