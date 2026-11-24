#!/bin/bash
sleep 20; for p in 8091 8090 8084 8104 8500; do echo -n "$p=$(curl -s -m4 -o /dev/null -w %{http_code} 127.0.0.1:$p/health) "; done; echo
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; pgrep -af "bin/sd " | cut -c1-120
tail -5 /workspace/nox/agent/out/web_server.log | cut -c1-200; tail -3 /workspace/nox/agent/out/web_watchdog.log
python3 - <<'P'
import json,urllib.request,time
b={"model":"nox-helion:latest","stream":True,"nox_mode":"fast","messages":[{"role":"user","content":"Привет! Как ты?"}]}; s=time.time(); acc=""
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=120)
    for line in r:
        try: acc+=(json.loads(line).get("message") or {}).get("content","")
        except Exception: pass
except Exception as e: acc="ERR %s"%e
print("chat %.0fs ::"%(time.time()-s), acc[-200:])
P
