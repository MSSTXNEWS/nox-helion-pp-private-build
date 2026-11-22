#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/fd.py -o /tmp/fd.py && python3 /tmp/fd.py
python3 /root/nox/env_restart.py 8082 NOX_CORE=1 | tail -1; python3 /root/nox/restart_same.py 8091 | tail -1; sleep 6
python3 - <<'P'
import json,urllib.request,time
for mode,q in (("fast","Привет, как ты?"),("fast","Как тебя ускорить? Что конкретно тормозит?"),("fast","Привет!"),("deep","Почему небо голубое?")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""; first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
    for line in r:
        try: c=json.loads(line).get("message",{}).get("content","")
        except Exception: c=""
        if c and "читает" not in c and first is None: first=time.time()-t
        txt+=c
    print("## %s first %.1f total %.1f"%(mode,first or -1,time.time()-t), q, "::", txt[-450:].replace("\n"," "))
P
