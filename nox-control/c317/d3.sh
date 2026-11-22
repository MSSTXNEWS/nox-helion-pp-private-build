#!/bin/bash
pkill -f flash_bench.py; sleep 3
cat > /root/nox/d3.py <<'P'
import json,urllib.request,time
SOUL=open("/root/nox/dl/v7/core/nox_wow/soul_prompt_ru.txt",encoding="utf-8").read()
def q(extra, content="Скучно. Нечего делать.", sysm=None, mt=220):
    m=([{"role":"system","content":sysm}] if sysm else [])+[{"role":"user","content":content}]
    b={"model":"x","messages":m,"max_tokens":mt,"temperature":0.3,"cache_prompt":True}; b.update(extra)
    t=time.time(); d=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
    m=d["choices"][0]["message"]; print(extra, "|content",len(m.get("content") or ""),repr((m.get("content") or "")[:70]),"|reas",len(m.get("reasoning_content") or ""), "|fin",d["choices"][0]["finish_reason"], round(time.time()-t), flush=True)
for e in ({"reasoning_effort":"minimal"},{"chat_template_kwargs":{"reasoning_effort":"minimal"}},{"chat_template_kwargs":{"enable_thinking":False,"clear_thinking":True}}):
    q(e)
q({}, sysm=SOUL)
q({"reasoning_effort":"minimal"}, sysm=SOUL)
P
nohup setsid python3 /root/nox/d3.py > /root/nox/logs/d3.log 2>&1 < /dev/null &
echo bg
