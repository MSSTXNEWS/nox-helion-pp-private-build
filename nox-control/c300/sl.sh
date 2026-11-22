#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/sl.py -o /tmp/sl.py && python3 /tmp/sl.py
python3 /root/nox/restart_same.py 8091 | tail -1; sleep 4
python3 - <<'P'
import json,urllib.request,time
for q in ("привет","как дела?","что нового?"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":"deep","stream":True}
    t=time.time(); txt=""; first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=250)
    for line in r:
        try: c=json.loads(line).get("message",{}).get("content","")
        except Exception: c=""
        if c and "читает" not in c and first is None: first=time.time()-t
        txt+=c
    print(q,"| first %.0fs total %.0fs |"%(first or -1,time.time()-t), txt[-120:].replace("\n"," "))
P
grep "prompt eval time" /root/nox/logs/glm_8081.log | tail -3 | cut -c40-160
