#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/mg.py -o /tmp/mg.py && python3 /tmp/mg.py
python3 /root/nox/restart_same.py 8091 | tail -1; sleep 4
for u in /api/health /api/pc-metrics /api/sys; do echo "$u $(curl -s -m10 -o /tmp/u.b -w '%{http_code}' http://127.0.0.1:8091$u) $(head -c 120 /tmp/u.b)"; done
python3 - <<'P'
import json,urllib.request,time
for mode,q in (("deep","Как тебя ускорить?"),("fast","Привет")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=250)
    for line in r:
        try: txt+=json.loads(line).get("message",{}).get("content","")
        except Exception: pass
    print(mode,"%.0fs"%(time.time()-t),txt[-300:].replace("\n"," "))
P
