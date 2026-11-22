#!/bin/bash
python3 - <<'P'
import json,urllib.request,time
b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Как тебя ускорить? Что конкретно тормозит?"}],"mode":"deep","stream":True}
t=time.time()
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
for line in r: print("%.1f"%(time.time()-t), line.decode()[:220].strip())
P
tail -4 /root/nox/logs/glm_8081.log | cut -c1-170; tail -5 /root/nox/logs/web_server.log | cut -c1-200
