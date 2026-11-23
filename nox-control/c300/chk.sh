#!/bin/bash
date -u +%T; cat /proc/loadavg
for p in 8091 8082 8083 8081 8093 8094 8095; do echo -n "$p=$(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:$p/health) "; done; echo
for p in $(pgrep -f 'llama-server.*port 808[13]'); do ps -o etimes=,args= -p $p | cut -c1-300; done
echo "start_glm: $(grep -o 'llama.cpp-[a-z]*\|spec-type[^ ]* [^ ]*\|-ngl [0-9]*\|taskset -c [0-9-]*' /root/nox/start_glm.sh | tr '\n' ' ')"
echo "web: dmem=$(grep -c '_dmem()' /root/nox/web_server.py) fdir=$(grep -c '_fdir' /root/nox/web_server.py) pcm=$(grep -c pc_metrics /root/nox/web_server.py) chat_mode_js=$(grep -c nox_mode /root/nox/web/chat.html) tts_ru=$(tr '\0' '\n' </proc/$(ss -ltnp | grep ':8094 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/environ | grep -c ruslan)"
tail -3 /root/nox/logs/glm_watch.log 2>/dev/null
python3 - <<'P'
import json,urllib.request,time,base64
for mode,q in (("fast","Привет!"),("fast","Как тебя ускорить?"),("deep","Почему небо голубое?")):
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
    print("## %s first %.1f total %.1f"%(mode,first or -1,time.time()-t), q, "::", txt[-260:].replace("\n"," "))
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8094/synth",json.dumps({"text":"Привет, я NOX.","lang":"ru"}).encode(),{"Content-Type":"application/json"}),timeout=60)
    pcm=b""
    for line in r:
        l=line.decode().strip()
        if l.startswith("data:"):
            d=json.loads(l[5:]); 
            if d.get("type")=="audio": pcm+=base64.b64decode(d["pcm_b64"])
    print("tts bytes",len(pcm))
except Exception as e: print("tts ERR",e)
P
