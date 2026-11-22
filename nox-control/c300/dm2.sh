#!/bin/bash
W=/root/nox/web_server.py
sed -i 's/^_DMEM_OBJ = \[None, 0.0\]$/import subprocess, time\n_DMEM_OBJ = [None, 0.0]/' $W
python3 -m py_compile $W && echo compiled && python3 /root/nox/restart_same.py 8091 | tail -1; sleep 5
python3 - <<'P'
import json,urllib.request,time
def ask(mode,text,hist=None):
    b={"model":"nox-helion:latest","messages":(hist or [])+[{"role":"user","content":text}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=250)
    for line in r:
        try: txt+=json.loads(line).get("message",{}).get("content","")
        except Exception: pass
    return "%.0fs %s"%(time.time()-t,txt[-220:].replace("\n"," "))
print("1 fast:", ask("fast","Запомни, пожалуйста: мою черепаху зовут Тортилла-7, ей 12 лет."))
time.sleep(8)
print("2 deep:", ask("deep","Как зовут мою черепаху и сколько ей лет?"))
time.sleep(5)
print("3 deep:", ask("deep","Запомни: мой любимый город — Тромсё."))
time.sleep(10)
print("4 fast:", ask("fast","Какой мой любимый город?"))
P
grep "deep-mem" /root/nox/logs/web_server.log | tail -3 | cut -c1-200
