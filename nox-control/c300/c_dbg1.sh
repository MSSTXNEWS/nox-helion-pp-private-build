echo "C300: c_dbg1"
N=/workspace/nox; P=$N/svc/pipeline
curl -s -m3 localhost:18217/quota; echo; curl -s -m3 localhost:8200/running | cut -c1-300; echo
tail -8 $N/state/pipe_err.log | cut -c1-300
cat > /tmp/ev.py <<'PY'
import sys,json,urllib.request,time
b={"conversation_id":"dbg%d"%time.time(),"message":sys.argv[1]}
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
t=time.time()
try:
    for l in urllib.request.urlopen(rq,timeout=100):
        l=l.decode("utf-8","replace").strip()
        if l and '"delta"' not in l: print(round(time.time()-t,1),l[:260])
        elif l: print(round(time.time()-t,1),"delta",l[:80])
except Exception as e: print("ERR",e)
PY
for q in "Кто написал Евгения Онегина?" "Сколько планет в Солнечной системе?"; do echo "== $q"; timeout 105 python3 /tmp/ev.py "$q"; done
curl -s -m3 localhost:18217/quota; echo; tail -5 $N/state/pipe_err.log | cut -c1-300
