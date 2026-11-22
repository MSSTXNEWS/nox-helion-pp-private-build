#!/bin/bash
grep -n 'nox_mode' /root/nox/web_server.py | head -5 | cut -c1-200
python3 - <<'P'
import json,urllib.request,time
for extra in ({}, {"nox_mode":"fast"}):
    b=dict({"messages":[{"role":"user","content":"Привет, как ты?"}],"max_tokens":80,"stream":False}, **extra)
    s=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8082/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200))
    n=r.get("nox",{}); print(extra, "%.1fs"%(time.time()-s), n.get("path"), n.get("tier"), "::", r["choices"][0]["message"]["content"][:150].replace("\n"," "))
P
