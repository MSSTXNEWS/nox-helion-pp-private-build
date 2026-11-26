echo "C300: srv_k141"
cd /workspace/nox; date -u +%T; uptime | sed 's/.*load/load/'
ps -eo pid,pcpu,nlwp,etimes,args --sort=-pcpu | head -14 | cut -c1-150
ls -la --time-style=+%T agent/LIVE_TURN state/orch/OWNER_ACTIVE 2>&1 | cut -c1-120
python3 - <<'PY'
import json,time,urllib.request
for i in range(2):
    b={"model":"x","stream":True,"max_tokens":16,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":"Привет! Ответь одним словом."}]}
    t=time.time(); first=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"}),timeout=100)
        for l in r:
            if l.startswith(b"data:") and b'"content"' in l and b'"content":""' not in l: first=round(time.time()-t,2); break
    except Exception as e: first=repr(e)[:60]
    print("8104 direct под нагрузкой:",first)
PY
curl -s -m5 http://127.0.0.1:8104/slots | python3 -c "import sys,json; d=json.load(sys.stdin); print([(s['id'],s.get('is_processing')) for s in d])" 2>&1 | head -2
tail -n 4 web/pkg/server/*.log 2>/dev/null | cut -c1-160 | tail -6
