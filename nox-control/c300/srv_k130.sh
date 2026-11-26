echo "C300: srv_k130"
cd /workspace/nox
pgrep -fa "autotrain" | grep -v pgrep | cut -c1-120 | head -3; ls -t agent/out | head -5; ls -la --time-style=+%T agent/autotrain/rounds | tail -3
tail -n 4 agent/out/autotrain.log | cut -c1-160; ls state/core/ 2>/dev/null | grep -i -E "pause|stop|disk" ; ls state/orch/pause state/orch/PAUSE* 2>&1 | head -3; ls ops/v5_knowledge_gpu_20261125/PAUSE_MAIN 2>&1|head -1
echo "--- 8510 TTFT"
python3 - <<'PY'
import json,time,urllib.request
for i in range(3):
    b={"model":"x","stream":True,"max_tokens":16,"messages":[{"role":"user","content":"Привет! Ответь одним словом."}]}
    t=time.time(); first=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8510/v1/chat/completions",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"}),timeout=90)
        for l in r:
            n+=1
            if first is None and l.startswith(b"data:") and b"content" in l and b'"content":""' not in l: first=round(time.time()-t,2); print("первый токен",first,l[:120]); break
        print("итог", first, "строк", n)
    except Exception as e: print("ERR",repr(e)[:100], round(time.time()-t,1))
PY
grep -n "def \|LIVE_TURN\|:8104\|:8300\|8400\|stream" agent/adapter.py | cut -c1-150 | head -60
