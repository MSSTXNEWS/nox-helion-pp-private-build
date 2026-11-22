#!/bin/bash
date -u +%T; cat /proc/loadavg; for p in $(pgrep -f 'llama-server.*port 808[13]'); do ps -o etimes=,pcpu=,args= -p $p | cut -c1-330; done
ps -eo pcpu,etimes,args --sort=-pcpu | sed -n 2,7p | cut -c1-130
python3 - <<'P'
import json,urllib.request,time
for mode in ("fast","deep"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Привет, как ты?"}],"mode":mode,"stream":True}
    t=time.time(); txt=""; first=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
        for line in r:
            try: c=json.loads(line).get("message",{}).get("content","")
            except Exception: c=""
            if c and "читает" not in c and first is None: first=time.time()-t
            txt+=c
    except Exception as e: txt="ERR %s"%e
    print(mode,"first %.1f total %.1f"%(first or -1,time.time()-t),txt[-120:].replace("\n"," "))
P
