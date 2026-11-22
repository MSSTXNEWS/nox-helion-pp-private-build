#!/bin/bash
grep -nE '_mode *=|body.get\(|d.get\("(messages|mode|options)' /root/nox/web_server.py | head -12 | cut -c1-160
python3 - <<'P'
import json,urllib.request,time
for mode in ("fast","deep"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Привет! Кто ты? Ответь одной фразой."}],"mode":mode,"stream":True}
    t=time.time(); txt=""; ph=[]
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
        for line in r:
            try: d=json.loads(line)
            except Exception: continue
            txt+=d.get("message",{}).get("content","")
            if d.get("nox_phase"): ph.append(d["nox_phase"].get("phase")+":"+str(d["nox_phase"].get("why","")))
        print(mode,"%.0fs"%(time.time()-t),set(ph),txt[-250:].replace("\n"," "))
    except Exception as e: print(mode,"ERR",e)
P
