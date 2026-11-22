#!/bin/bash
python3 -I - <<'PY'
import json,urllib.request,threading,time,uuid,re
def web(q,mode=None):
    b={"messages":[{"role":"user","content":q}],"stream":True}
    if mode:b["nox_mode"]=mode
    r=urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"})
    t="";ph=[];t0=time.time();first=None
    try:
        for l in urllib.request.urlopen(r,timeout=120):
            try:o=json.loads(l)
            except Exception:continue
            c=(o.get("message") or {}).get("content","")
            if c and first is None:first=round(time.time()-t0,1)
            t+=c
            if o.get("nox_phase"):ph.append(str(o["nox_phase"])[:30])
    except Exception as e:t+="[ERR %s]"%str(e)[:60]
    return t,first,ph[:2]
for q in ["привет","привет","привет","как сервер?","удали прошлые запросы"]:
    t,f,p=web(q); print("Q",q,"| ttft",f,"|",repr(t[:230]),p)
bad=re.compile(r"готовлю в фоне|Быстрый слой ответил пусто|Жду твой ввод|Что хочешь")
# STOP на CORE
tid=str(uuid.uuid4()); got={"n":0}
def run():
    b={"messages":[{"role":"user","content":"Напиши очень длинный подробный рассказ про море, не меньше 900 слов."}],"stream":True,"nox_mode":"fast","nox_turn_id":tid,"nox_conversation_id":"A-stop"}
    r=urllib.request.Request("http://127.0.0.1:8090/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"})
    try:
        for l in urllib.request.urlopen(r,timeout=60):
            if l.startswith(b"data:"):got["n"]+=1
    except Exception as e:got["e"]=str(e)[:50]
th=threading.Thread(target=run);th.start();time.sleep(3)
r=urllib.request.Request("http://127.0.0.1:8090/v1/stop",json.dumps({"turn_id":tid}).encode(),{"Content-Type":"application/json"})
try:print("STOP ->",urllib.request.urlopen(r,timeout=10).read()[:400].decode())
except Exception as e:print("STOP err",e)
th.join(20);print("chunks",got)
print("core health",urllib.request.urlopen("http://127.0.0.1:8090/health").read()[:260].decode())
PY
grep -c "готовлю в фоне" /root/nox/web_server.py; grep -h "verdict\|conscience" -m3 /root/nox/state/v7/core_trace/* 2>/dev/null | tail -2 | cut -c1-200
