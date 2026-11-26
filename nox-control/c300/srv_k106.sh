echo "C300: srv_k106"
cd /workspace/nox; F=imgsvc/image_service.py
cp -n $F $F.bak_k1_owner2_$(date +%Y%m%d)
python3 - <<'PY'
import re
F="/workspace/nox/imgsvc/image_service.py"; s=open(F).read()
if "_k1_owner()" in s: print("уже"); raise SystemExit
s=s.replace("def handle_generate(body):", '''def _k1_owner():
    try:
        return time.time() - os.path.getmtime(os.path.join(N, "state", "orch", "OWNER_ACTIVE")) < 180 and not os.path.exists(os.path.join(N, "state", "draw_local_off"))
    except OSError:
        return False


def handle_generate(body):''',1)
m=re.search(r'^(\s*)return self\._send\(503, \{"error": "stop_flag"\}\)', s, re.M)
ind=m.group(1)
s=s[:m.start()]+ind+'if not _k1_owner():\n'+ind+'    return self._send(503, {"error": "stop_flag"})'+s[m.end():]
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled; sed -n 258,266p $F
pid=$(pgrep -f "imgsvc/image_service.py" | head -1); python3 /tmp/relaunch.py $pid /workspace/nox/imgsvc/restart_k1.log 2>&1 | tail -2
sleep 3; touch state/orch/OWNER_ACTIVE
python3 - <<'PY'
import json,time,urllib.request
t=time.time()
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/img/generate",data=json.dumps({"prompt":"кот в космосе, астронавт, звёзды","width":768,"height":768}).encode(),headers={"Content-Type":"application/json"}),timeout=170)
    b=r.read(); st=r.status
except urllib.error.HTTPError as e: b=e.read(); st=e.code
except Exception as e: b=repr(e).encode(); st=0
print("status",st,"sec %.1f"%(time.time()-t),"len",len(b)); print(b[:250])
PY
