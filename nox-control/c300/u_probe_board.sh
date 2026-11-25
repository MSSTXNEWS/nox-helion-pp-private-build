echo "C300: u_probe_board"
R=/workspace/nox/web/pkg/server/svc_registry.json
python3 - <<'PYX'
import json
R='/workspace/nox/web/pkg/server/svc_registry.json';d=json.load(open(R,encoding='utf-8'))
print('agents',d.get('agents'),'advisors',d.get('advisors'))
if 'agentsb' not in d: d['agentsb']={'port':8810,'mode':'strip','title':'NOX agents board','ui':False}
json.dump(d,open(R,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
PYX
sleep 2
curl -s -m 8 localhost:8810/board | head -c 2500; echo
echo "-- via proxy: $(curl -s -m 8 -o /dev/null -w '%{http_code}' localhost:8091/svc/agentsb/board)"
ID=$(curl -s -m 8 localhost:8810/board | python3 -c "
import sys,json
d=json.load(sys.stdin)
def f(o):
  if isinstance(o,dict):
    for k in ('id','task_id'):
      if isinstance(o.get(k),(str,int)): return o[k]
    for v in o.values():
      r=f(v)
      if r: return r
  if isinstance(o,list):
    for v in o:
      r=f(v)
      if r: return r
print(f(d) or '')")
echo "id=$ID"; curl -s -m 8 localhost:8810/task/$ID/card | head -c 1500; echo
echo "-- widgets column in chat"; grep -o 'id="[a-zA-Z]*[Ww]id[a-zA-Z]*"' /workspace/nox/web/site/chat.html | head; grep -o "class=\"[^\"]*widg[^\"]*\"" /workspace/nox/web/site/chat.html | head -5
echo done
