echo "K1: diag_cx1"
echo "8104 health=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) load=$(cut -d' ' -f1 /proc/loadavg)"
curl -s -m 5 http://127.0.0.1:8104/slots | python3 -c "import json,sys;d=json.load(sys.stdin);print('slots_busy',sum(1 for s in d if s.get('is_processing')),'of',len(d))" 2>/dev/null
ps -eo pcpu,comm --sort=-pcpu | head -8
python3 - <<'PY'
import json,urllib.request,uuid
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":"привет","mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
    for ln in r:
        s=ln.decode("utf8","replace").strip()
        if not s: continue
        o=json.loads(s); t=o.get("t") or o.get("type")
        if t=="error": print("ERRCODE",o.get("code"))
        if t=="stage": print("STAGE",o.get("code"))
        if t in("done","error"): print("END",t); break
except Exception as e: print("EXC",type(e).__name__)
PY
