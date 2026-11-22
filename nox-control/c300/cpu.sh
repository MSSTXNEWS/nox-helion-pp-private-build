#!/bin/bash
ps -eo pcpu,args --sort=-pcpu | head -6 | cut -c1-110
cp /root/nox/start_glm.sh /root/nox/start_glm.sh.t26
sed -i -E 's/nohup nice -n [0-9]+ (taskset -c [0-9,-]+ )?/nohup nice -n 19 taskset -c 0-17 /; s/-t 26 -tb 26/-t 18 -tb 18/' /root/nox/start_glm.sh
grep -o "nice.*taskset -c [0-9-]*\|-t [0-9]* -tb [0-9]*" /root/nox/start_glm.sh
bash /root/nox/start_glm.sh; for i in $(seq 40); do sleep 3; curl -sf -m2 127.0.0.1:8081/health >/dev/null && break; done; echo "glm up ${i}x3s"
python3 - <<'P'
import json,urllib.request,time
for mode in ("fast","fast"):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Привет! Кто ты? Одной фразой."}],"mode":mode,"stream":True}
    t=time.time(); txt=""; first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
    for line in r:
        try: c=json.loads(line).get("message",{}).get("content","")
        except Exception: c=""
        if c and first is None: first=time.time()-t
        txt+=c
    print(mode,"first %.1fs total %.1fs"%(first or -1,time.time()-t),txt[-150:].replace("\n"," "))
P
cat /proc/loadavg
