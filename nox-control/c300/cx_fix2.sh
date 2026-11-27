echo "K1: cx_fix2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; S=$N/web/pkg/server
python3 - <<'PY'
import json,time,urllib.request
t0=time.time();first=None
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":"Привет"}],"max_tokens":20,"stream":True}).encode(),{"Content-Type":"application/json"}),timeout=60)
for ln in r:
    if b'"content"' in ln and first is None: first=time.time()-t0
print("direct8104_ttft",None if first is None else round(first,2),"total",round(time.time()-t0,1))
PY
ls -1t $S/chat_core.py.bak_rs* 2>/dev/null | sed 's|.*/||' | head -6
B=$(ls -1tr $S/chat_core.py.bak_rsdeep_* 2>/dev/null | head -1)
if [ -n "$B" ]; then cp -a $S/chat_core.py $S/chat_core.py.bak_cxfix2_$(date +%s); cp -a "$B" $S/chat_core.py; python3 -m py_compile $S/chat_core.py && echo "restored $(basename $B)"; fi
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 5
python3 - <<'PY'
import json,urllib.request,uuid,time
for q in ("привет","Как ты ко мне обращаешься?"):
    t0=time.time();first=None;n=0;end=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s); t=o.get("t")
        if t=="delta":
            n+=1
            if first is None: first=time.time()-t0
        if t in("done","error"): end=t; break
    print("TURN ttft",None if first is None else round(first,1),"deltas",n,"end",end)
PY
