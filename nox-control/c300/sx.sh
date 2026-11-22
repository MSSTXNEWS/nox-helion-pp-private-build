#!/bin/bash
S=/root/nox/repo/nox-control/qs6/soul_prompt_ru.txt; grep -n "отклик\|коротк\|кратк\|Говори\|лаконич\|афоризм\|одной фраз" $S | cut -c1-220 | head -12
python3 - <<'P'
import json,urllib.request,time
def ask(sysm, q, temp=None):
    b={"messages":[{"role":"system","content":sysm},{"role":"user","content":q}],"max_tokens":300,"chat_template_kwargs":{"enable_thinking":False}}
    if temp is not None: b["temperature"]=temp
    t=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=300))
    return "%.0fs %s"%(time.time()-t, r["choices"][0]["message"]["content"][:500].replace("\n"," "))
q="Как тебя ускорить? Что конкретно тормозит?"
print("PLAIN:", ask("Ты — NOX, ИИ-помощник на сервере с GLM-5.3-Flash (RTX 5060 Ti 16 ГБ, Xeon). Отвечай по-русски, конкретно.", q))
P
