#!/bin/bash
pkill -f flash_bench.py; sleep 3
python3 - <<'P'
import json,urllib.request,time
def q(extra, content="Скучно. Нечего делать.", sysm=None):
    m=([{"role":"system","content":sysm}] if sysm else [])+[{"role":"user","content":content}]
    b={"model":"x","messages":m,"max_tokens":160,"temperature":0.3,"cache_prompt":True}; b.update(extra)
    t=time.time(); d=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=600))
    m=d["choices"][0]["message"]; print(extra, "keys",list(m.keys()),"content",repr((m.get("content") or "")[:120]),"reas",repr((m.get("reasoning_content") or "")[:80]), "fin",d["choices"][0]["finish_reason"], round(time.time()-t))
q({"chat_template_kwargs":{"enable_thinking":False}})
q({"chat_template_kwargs":{"enable_thinking":False}, "reasoning_format":"none"})
q({"reasoning_budget":0})
q({"chat_template_kwargs":{"enable_thinking":False},"reasoning_budget":0})
P
grep -a -i -E "chat template|thinking|reasoning" /root/nox/logs/glm_8081.log | head -5 | cut -c1-250
