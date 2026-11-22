#!/bin/bash
for i in $(seq 20); do curl -sf -m2 127.0.0.1:8081/health >/dev/null && break; sleep 3; done
echo "glm $(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:8081/health) watch=$(pgrep -f glm_watch.sh | wc -l)"; grep -o "spec-type[^>]*" /root/nox/start_glm.sh | cut -c1-80; cat /proc/loadavg
python3 - <<'P'
import json,urllib.request,time
for mode,q in (("fast","Привет!"),("fast","Как тебя ускорить?"),("deep","Привет, что нового?"),("deep","Почему небо голубое?")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""; first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
    for line in r:
        try: c=json.loads(line).get("message",{}).get("content","")
        except Exception: c=""
        if c and "читает" not in c and first is None: first=time.time()-t
        txt+=c
    print("## %s first %.1f total %.1f"%(mode,first or -1,time.time()-t), q, "::", txt[-300:].replace("\n"," "))
P
