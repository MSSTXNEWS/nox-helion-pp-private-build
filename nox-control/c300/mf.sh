#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/mem_filter.py -o /tmp/mem_filter.py && curl -fsSL $R/mf.py -o /tmp/mf.py && python3 /tmp/mf.py
cd /root/nox/repo/nox-control && python3 -c "from qs6.mem_filter import clean; print(clean(['3 на GPU1 (OOM)','a1efe42e: постоянная память','name_en: Adrian','Создателя зовут Иван']))"
python3 /root/nox/restart_same.py 8091 | tail -1; python3 /root/nox/restart_same.py 8082 | tail -1; sleep 8
python3 - <<'P'
import json,urllib.request,time
for mode,q in (("deep","привет"),("deep","Как тебя ускорить? Что конкретно тормозит?"),("fast","Как тебя ускорить?")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
    for line in r:
        try: txt+=json.loads(line).get("message",{}).get("content","")
        except Exception: pass
    print("##",mode,q,"%.0fs"%(time.time()-t),"::",txt[-700:].replace("\n"," "))
P
