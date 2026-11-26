echo "C300: srv_k129"
cd /workspace/nox; date -u +%T; ls STOP 2>&1|head -1
pgrep -fa "distill_v2.py (train|gen|judge|prep)" | cut -c1-110 | head -3; tail -n 3 agent/out/autotrain.log | cut -c1-200
echo "--- 8104 args"; tr '\0' ' ' < /proc/$(pgrep -f "port 8104" | head -1)/cmdline | cut -c1-600; echo
echo "--- affinity"; for p in $(pgrep -f "port 8141|judge_service|distill_v2.py train"); do echo "$p $(taskset -cp $p 2>&1 | sed 's/.*: //') $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-70)"; done
nproc; lscpu | grep -i "model name\|^CPU(s)\|Thread"
echo "--- TTFT"
python3 - <<'PY'
import json,time,urllib.request
def ttft(url,model=None,extra=None):
    b={"model":model or "x","stream":True,"max_tokens":16,"messages":[{"role":"user","content":"Привет! Ответь одним словом."}]}
    if extra: b.update(extra)
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(b).encode(),headers={"Content-Type":"application/json"}),timeout=60)
        for l in r:
            if l.startswith(b"data:") and b'"content"' in l and b'"content":""' not in l and b'"content": ""' not in l: return round(time.time()-t,2)
    except Exception as e: return repr(e)[:80]
    return None
for i in range(3): print("8104 direct", ttft("http://127.0.0.1:8104/v1/chat/completions",extra={"chat_template_kwargs":{"enable_thinking":False}}))
PY
grep -n "8104\|stream" agent/adapter.py 2>/dev/null | head -12 | cut -c1-160
