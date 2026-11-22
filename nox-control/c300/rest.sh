#!/bin/bash
cd /root/nox; curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rest.py -o /tmp/rest.py && python3 /tmp/rest.py
cmp -s /root/nox/web_server.py.bak_20261122120055 /root/nox/repo/nox-control/s1web/web_server.py && echo "small == repo s1web"
python3 /root/nox/restart_same.py 8091 2>&1 | tail -1; sleep 5
curl -s -m5 127.0.0.1:8091/api/sys | head -c 300; echo
python3 - <<'P'
import json,urllib.request,time
bad=0
for mode in ("fast","deep"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Привет! Кто ты? Одной фразой."}],"mode":mode,"stream":True}
    t=time.time(); txt=""
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
        for line in r:
            try: txt+=json.loads(line).get("message",{}).get("content","")
            except Exception: pass
    except Exception as e: txt="ERR %s"%e
    print(mode,"%.0fs"%(time.time()-t),txt[-200:].replace("\n"," "))
    if len(txt.strip())<5 or txt.startswith("ERR"): bad=1
open("/tmp/chatbad","w").write(str(bad))
P
if [ "$(cat /tmp/chatbad)" = "1" ]; then cp $(ls -t /root/nox/web_server.py.small_* | head -1) /root/nox/web_server.py; python3 /root/nox/restart_same.py 8091 | tail -1; echo ROLLED BACK; fi
