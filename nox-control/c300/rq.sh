#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rq.py -o /tmp/rq.py && python3 /tmp/rq.py
python3 /root/nox/restart_same.py 8091 | tail -1; sleep 4
python3 - <<'P'
import json,urllib.request,time
for mode,q in (("deep","привет"),("deep","Как тебя ускорить? Что конкретно тормозит?"),("fast","Как тебя ускорить?")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
    for line in r:
        try: txt+=json.loads(line).get("message",{}).get("content","")
        except Exception: pass
    print("##",mode,q,"%.0fs"%(time.time()-t),"::",txt[-600:].replace("\n"," "))
P
