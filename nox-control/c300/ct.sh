#!/bin/bash
python3 - <<'P'
import json,urllib.request,time
def t(msgs):
    b={"model":"nox-helion:latest","stream":True,"nox_mode":"fast","messages":msgs}; s=time.time(); acc=""; first=None; last=""
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=150)
        for line in r:
            last=line.decode()[:200]
            try: d=json.loads(line); c=(d.get("message") or {}).get("content","")
            except Exception: c=""
            if c and first is None: first=time.time()-s
            acc+=c
    except Exception as e: acc="ERR %s"%e
    return "first %s total %.0fs :: %s || last=%s"%(first and round(first,1), time.time()-s, acc[-160:].replace("\n"," "), last.strip()[:160])
print("plain:", t([{"role":"user","content":"Нарисуй домик в горах"}]))
print("system:", t([{"role":"system","content":"Если просят нарисовать — последней строкой GEN: <prompt>"},{"role":"user","content":"Нарисуй домик в горах"}]))
P
cat /proc/loadavg; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
