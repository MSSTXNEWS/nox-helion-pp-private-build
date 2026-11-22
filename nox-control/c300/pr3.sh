#!/bin/bash
V=/root/nox/dl/v7/core/nox_wow; W=/root/nox/repo/nox-control/wow7; added=""
for d in CON PER EMO WORLD CTX; do if [ -d $V/$d ] && [ ! -e $W/$d ]; then cp -r $V/$d $W/$d && added="$added $d"; fi; done
echo "added:$added"; echo "$added" > /root/nox/state/prime_added_dirs.txt
python3 /root/nox/restart_same.py 8082 | tail -1; sleep 8
grep "\[prime\]" /root/nox/logs/gateway.log | tail -8 | cut -c1-160
python3 - <<'P'
import json,urllib.request,time
bad=0
for q in ("Привет! Как ты сегодня?","Что ты сейчас чувствуешь, одной фразой?"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":"fast","stream":True}
    t=time.time(); txt=""
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=120)
        for line in r:
            try: d=json.loads(line); txt+=d.get("message",{}).get("content","")
            except Exception: pass
    except Exception as e: txt="ERR %s"%e
    print("%.0fs"%(time.time()-t), txt[-200:].replace("\n"," "))
    if len(txt.strip())<3 or txt.startswith("ERR"): bad=1
open("/tmp/prbad","w").write(str(bad))
P
if [ "$(cat /tmp/prbad)" = "1" ]; then for d in $(cat /root/nox/state/prime_added_dirs.txt); do rm -rf /root/nox/repo/nox-control/wow7/$d; done; python3 /root/nox/restart_same.py 8082 | tail -1; echo ROLLED BACK; fi
