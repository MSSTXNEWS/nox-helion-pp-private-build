echo "C300: srv_k104"
cd /workspace/nox; touch state/orch/OWNER_ACTIVE
python3 - <<'PY'
import json,time,urllib.request,base64,os
t=time.time()
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/img/generate",data=json.dumps({"prompt":"кот в космосе, астронавт, звёзды","width":768,"height":768}).encode(),headers={"Content-Type":"application/json"}),timeout=200)
    b=r.read(); st=r.status
except urllib.error.HTTPError as e: b=e.read(); st=e.code
print("status",st,"sec %.1f"%(time.time()-t),"len",len(b)); print(b[:300])
try:
    j=json.loads(b); print({k:(v if len(str(v))<120 else str(v)[:80]) for k,v in j.items()})
except Exception: pass
PY
tail -n 4 imgsvc/*.log 2>/dev/null | cut -c1-200 | tail -6
