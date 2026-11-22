#!/bin/bash
date -u +%T; cat /proc/loadavg
for p in $(pgrep -f 'llama-server.*port 808[13]'); do ps -o etimes=,pcpu=,args= -p $p | cut -c1-360; done
echo "start_glm: $(grep -v '^#' /root/nox/start_glm.sh | grep -o 'taskset -c [0-9,-]*\|-ngl [0-9]*\|-t [0-9]*\|--parallel [0-9]*\|-c [0-9]*\|-kvu' | tr '\n' ' ')"
for p in 8091 8082 8083 8081 8093 8094; do echo -n "$p=$(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/health) "; done; echo
grep -c nox_mode /root/nox/web/chat.html; grep -c "_dmem()" /root/nox/web_server.py; grep -c pc_metrics /root/nox/web_server.py
python3 - <<'P'
import json,urllib.request,time
b={"messages":[{"role":"user","content":"Расскажи коротко про Луну."}],"max_tokens":120,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}}
try:
    r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)); t=r.get("timings",{})
    print("GLM tg %.2f pp %.1f"%(t.get("predicted_per_second",0),t.get("prompt_per_second",0)))
except Exception as e: print("GLM ERR",e)
for mode,q in (("fast","Привет, как ты?"),("deep","Почему небо голубое?")):
    b={"model":"nox-helion:latest","messages":[{"role":"user","content":q}],"mode":mode,"stream":True}
    t=time.time(); txt=""; first=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/api/chat",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200)
        for line in r:
            try: c=json.loads(line).get("message",{}).get("content","")
            except Exception: c=""
            if c and "читает" not in c and first is None: first=time.time()-t
            txt+=c
    except Exception as e: txt="ERR %s"%e
    print(mode,"first %.1f total %.1f ::"%(first or -1,time.time()-t),txt[-200:].replace("\n"," "))
P
