#!/bin/bash
python3 /root/nox/env_restart.py 8082 NOX_CORE=0 | tail -1; sleep 8
python3 - <<'P'
import json,urllib.request,time
for q in ("Привет, как ты?","Как тебя ускорить? Что конкретно тормозит?","Как зовут моего Создателя?"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":"fast","stream":True}
    t=time.time(); txt=""
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
    for line in r:
        try: txt+=json.loads(line).get("message",{}).get("content","")
        except Exception: pass
    print("## %.1fs"%(time.time()-t), q, "::", txt[-400:].replace("\n"," "))
P
