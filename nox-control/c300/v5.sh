#!/bin/bash
for i in $(seq 30); do grep -q DONE /root/nox/logs/flash_ab4.log && break; sleep 8; done
tail -3 /root/nox/logs/flash_ab4.log; grep -o "ngl [0-9]*\|-t [0-9]*\|--parallel [0-9]*" /root/nox/start_glm.sh | tr '\n' ' '; echo; pgrep -f glm_watch.sh >/dev/null && echo watch on
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
python3 - <<'P'
import json,urllib.request,time
for mode in ("fast","deep"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Привет! Кто ты? Одной фразой."}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=150)
        for line in r:
            try: txt+=json.loads(line).get("message",{}).get("content","")
            except Exception: pass
    except Exception as e: txt="ERR %s"%e
    print(mode,"%.0fs"%(time.time()-t),txt[-150:].replace("\n"," "))
P
