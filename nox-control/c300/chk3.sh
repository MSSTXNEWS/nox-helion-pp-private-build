#!/bin/bash
date -u +%T; for p in 8081 8083 8091 8082; do echo "$p $(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/health)"; done
pgrep -af 'llama-server' | grep -o 'port [0-9]*.*' | cut -c1-120; grep -o "ngl [0-9]*\|-c [0-9]*" /root/nox/start_glm.sh | tr '\n' ' '; echo
python3 - <<'P'
import json,urllib.request,time
for mode in ("fast","deep"):
    b={"message":"Привет! Кто ты? Ответь одной фразой.","mode":mode}
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
        out=r.read().decode("utf-8","ignore")
        print(mode, "%.0fs"%(time.time()-t), out[-300:].replace("\n"," "))
    except Exception as e: print(mode,"ERR",e)
P
