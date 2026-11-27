echo "K1: v1_02g"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
date +%T; ss -ltnp | grep -E ":8091 |:18091 " | sed -E 's/users:\(\("([^"]*)",pid=([0-9]+).*/\1 \2/'
ps -eo pid,etimes,args | grep -E "web_server.py|selfheal" | grep -v grep | cut -c1-120
python3 - <<'PY'
import json,time,urllib.request,uuid
for cid in ("rv-"+uuid.uuid4().hex[:6],"qa-"+uuid.uuid4().hex[:6]):
    t0=time.time(); first=None; ev=[]
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":"Привет, как дела?","mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
        for ln in r:
            try: o=json.loads(ln)
            except Exception: continue
            k=o.get("t") or o.get("type") or o.get("event")
            if k=="delta" and first is None: first=time.time()-t0
            if k=="error": ev.append({a:str(b)[:120] for a,b in o.items()})
            if k in("done","error"): break
    except Exception as e: ev.append(type(e).__name__)
    print(cid[:2],"ttft",first and round(first,1),"sec",round(time.time()-t0,1),ev)
PY
tail -4 $N/state/chat_fast.log | cut -c1-80
echo END
