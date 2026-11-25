echo "C300: u_probe_notes"
cd /workspace/nox/web
grep -rn "api/notes" --include=*.py . 2>/dev/null | head -5
python3 - <<'PY'
import json,urllib.request
B='http://127.0.0.1:8091'
def get(): return json.load(urllib.request.urlopen(B+'/api/notes'))
def post(n):
  try:
    r=urllib.request.urlopen(urllib.request.Request(B+'/api/notes',json.dumps({'notes':n}).encode(),{'Content-Type':'application/json'}));return r.status,r.read()[:150]
  except Exception as e: return 'ERR',str(e)[:150],getattr(e,'read',lambda:b'')()[:200]
o=get().get('notes',[]);print('count',len(o))
print(post(o+[{'id':'pad-1999-01-01','text':'probe','ts':1.5,'proj':'x','pad':1}]));print([n for n in get()['notes'] if 'pad' in str(n['id'])])
print(post(o+[{'id':'padx','text':'probe2','ts':1}]));print([n for n in get()['notes'] if 'pad' in str(n['id'])])
post(o)
PY
