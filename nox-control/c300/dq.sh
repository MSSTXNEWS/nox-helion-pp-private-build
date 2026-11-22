#!/bin/bash
grep -E "print_timing|launch_slot" /root/nox/logs/glm_8081.log | tail -6 | cut -c1-170
python3 - <<'P'
import json,urllib.request,time
b={"model":"nox-helion:latest","messages":[{"role":"user","content":"Объясни, почему небо голубое?"}],"mode":"deep","stream":True}
t=time.time()
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280)
for line in r:
    d=json.loads(line); 
    if d.get("nox_phase") or d.get("done") or d.get("error"): print("%.1f"%(time.time()-t), json.dumps(d,ensure_ascii=False)[:250])
    elif d.get("message",{}).get("content"): print("%.1f"%(time.time()-t), repr(d["message"]["content"][:80]))
P
grep -E "print_timing" /root/nox/logs/glm_8081.log | tail -3 | cut -c1-170
