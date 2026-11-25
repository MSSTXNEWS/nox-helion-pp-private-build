#!/bin/bash
slots(){ curl -s -m 5 127.0.0.1:8104/slots | python3 -c "import sys,json;print('busy',sum(1 for s in json.load(sys.stdin) if s['is_processing']),'/3')"; }
echo "load $(cut -d' ' -f1-3 /proc/loadavg) idle $(top -bn2 -d3 | grep Cpu | tail -1 | sed 's/.*ni, *\([0-9.]*\) id.*/\1/')%"; slots
p=$(pgrep -f "tmp/t17_ttft10.py" | head -1); if [ -n "$p" ]; then echo "backup: $(tr '\0' ' ' </proc/$p/cmdline)" >> /workspace/nox/state/p3/killed.txt; kill $p; echo "killed stale t17 client $p"; fi
sleep 5; slots
cat >/tmp/p3_ttft.py <<'PY'
import json,time,http.client
for q in ("Привет! Одним предложением: как дела?","Расскажи в трёх предложениях о Севастополе."):
    t=time.time()
    try:
        c=http.client.HTTPConnection("127.0.0.1",8104,timeout=70)
        c.request("POST","/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":120,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}),{"Content-Type":"application/json"})
        r=c.getresponse();ft=None;n=0
        while True:
            l=r.readline()
            if not l:break
            if l.startswith(b"data:") and b'"delta"' in l and b'"content":"' in l and b'"content":""' not in l:
                n+=1
                if ft is None: ft=time.time()-t
        print("8104 first_token_s",ft and round(ft,2),"total_s",round(time.time()-t,1),"chunks",n)
    except Exception as e: print("ERR",type(e).__name__,round(time.time()-t,1))
PY
timeout 150 python3 /tmp/p3_ttft.py
slots; echo "load $(cut -d' ' -f1-3 /proc/loadavg)"; free -m | sed -n 2p
