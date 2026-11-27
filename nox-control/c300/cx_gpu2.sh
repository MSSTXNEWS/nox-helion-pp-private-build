echo "K1: cx_gpu2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain; ts=$(date +%s)
B=$A/donor_hybrid.cmd.liska_ncmoe22; G=$A/donor_hybrid.cmd.gpu_ncmoe0
python3 -c "import re,sys;s=open(sys.argv[1]).read();n=re.subn(r\"(--n-cpu-moe|-ncmoe)([ =\\t\"\x27\\xa0]+)[0-9]+\",lambda m:m.group(1)+m.group(2)+\"0\",s);open(sys.argv[2],\"w\").write(n[0]);print(\"subs\",n[1])" $B $G
grep -q -- "--n-cpu-moe 0" $G || { echo "NO_SUBST abort"; grep -c "cpu-moe" $B; echo END; exit 0; }
echo "variant: $(tr '\n' ' ' < $G | grep -oE -- '--n-cpu-moe [0-9]+|--parallel [0-9]+|-ngl [0-9]+|--n-gpu-layers [0-9]+' | tr '\n' ' ')"
echo "vram_before $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)"
bench(){ python3 - <<'PY'
import json,time,urllib.request
ctx=("Контекст: "+"NOX помогает Создателю с проектами, обучением, памятью и рисованием. "*22)
res=[]
for i in range(5):
    t0=time.time();first=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps({"messages":[{"role":"system","content":"Ты NOX."},{"role":"user","content":ctx+" Вопрос %d: кратко, что ты умеешь?"%i}],"max_tokens":40,"stream":True,"cache_prompt":False,"chat_template_kwargs":{"enable_thinking":False}}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            if b'"content"' in ln and first is None: first=time.time()-t0
    except Exception as e: pass
    res.append(None if first is None else round(first,2))
print("BENCH ttft",res)
PY
}
bench
ok=0; for k in 1 2 3; do bash $N/ops/body_restart.sh --force --cmd $G --reason "cx_gpu2: all experts on GPU (ncmoe0) for chat speed" 2>&1 | tail -1 | grep -q "ИТОГ: ok" && { ok=1; break; }; sleep 25; done; echo "restart_ok=$ok"
sleep 10
V=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -1); echo "vram_after $V"
pct=$(echo $V | awk -F', ' '{printf "%d", $1*100/$2}'); echo "vram_pct $pct"
out=$(bench); echo "$out"
med=$(echo "$out" | python3 -c "import sys,ast;a=[x for x in ast.literal_eval(sys.stdin.read().split('ttft',1)[1].strip()) if x];a.sort();print(a[len(a)//2] if a else 99)")
echo "med_ttft $med"
if [ $ok = 1 ] && [ $pct -le 88 ] && python3 -c "import sys;sys.exit(0 if float('$med')<1.5 else 1)"; then
  for f in donor_hybrid.cmd donor_hybrid.cmd.known_good; do cp -a $A/$f $A/$f.bak_cxgpu2_$ts; cp $G $A/$f; done; echo "PINNED gpu_ncmoe0"
else
  echo "ROLLBACK"; for k in 1 2 3; do bash $N/ops/body_restart.sh --force --cmd $B --reason "cx_gpu2 rollback to ncmoe22" 2>&1 | tail -1 | grep -q "ИТОГ: ok" && break; sleep 25; done; sleep 8; bench
fi
python3 - <<'PY'
import json,time,urllib.request,uuid
for q in ("привет","Сколько будет 17*23?","Объясни коротко, что такое DNS"):
    t0=time.time();first=None;end=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            s=ln.strip()
            if not s: continue
            o=json.loads(s); t=o.get("t")
            if t=="delta" and first is None: first=time.time()-t0
            if t in("done","error"): end=t; break
    except Exception as e: end=type(e).__name__
    print("TURN ttft",None if first is None else round(first,2),"total",round(time.time()-t0,1),"end",end)
PY
echo END
