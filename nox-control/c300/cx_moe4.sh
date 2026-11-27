echo "K1: cx_moe4"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain
F=$A/donor_hybrid.cmd.liska_ncmoe22
tr '\n' ' ' < $F | grep -oE -- '(-ot|--n-cpu-moe|-ncmoe|--parallel|-t) [^ ]+' | tr '\n' ' '; echo
grep -q -- "--parallel" $F || echo "WARN no parallel"
ok=0; for k in 1 2 3 4 5 6; do bash $N/ops/body_restart.sh --force --cmd $F --reason "cx_moe4: experts partly on GPU (ncmoe22), owner chat priority" 2>&1 | tail -1 | grep -q "ИТОГ: ok" && { ok=1; break; }; sleep 25; done; echo "restart_ok=$ok"
sleep 10
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
python3 - <<'PY'
import json,time,urllib.request,uuid
for i in range(3):
    t0=time.time();first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":"Привет, как дела?"}],"max_tokens":20,"stream":True}).encode(),{"Content-Type":"application/json"}),timeout=90)
    for ln in r:
        if b'"content"' in ln and first is None: first=time.time()-t0
    print("direct8104_ttft",None if first is None else round(first,2))
for q in ("привет","Как ты ко мне обращаешься?"):
    t0=time.time();first=None;end=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s); t=o.get("t")
        if t=="delta" and first is None: first=time.time()-t0
        if t in("done","error"): end=t; break
    print("TURN ttft",None if first is None else round(first,1),"end",end)
PY
