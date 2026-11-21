#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-260; }
for i in 1 2 3; do
 python3 - <<PY
import json,time,urllib.request
q=["Объясни простыми словами, что такое кэш процессора, в 5 предложениях.","Напиши функцию на Python, которая проверяет, является ли строка палиндромом, и объясни кратко.","Дай три совета, как быстрее выучить испанский язык."][$i-1]
body=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":96,"temperature":0,"stream":True,"stream_options":{"include_usage":True}}).encode()
req=urllib.request.Request("http://127.0.0.1:8098/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
t0=time.time();first=None;n=0;last=None
try:
  with urllib.request.urlopen(req,timeout=240) as r:
    for line in r:
        line=line.decode().strip()
        if not line.startswith("data:") or line.endswith("[DONE]"): continue
        d=json.loads(line[5:])
        ch=d.get("choices") or []
        if ch and (ch[0].get("delta",{}).get("content") or ch[0].get("delta",{}).get("reasoning_content")):
            n+=1
            if first is None: first=time.time()-t0
            last=time.time()
        if d.get("usage"): u=d["usage"]
  tot=(last or time.time())-t0
  print("run $i ttft_s",round(first or -1,2),"chunks",n,"gen_s",round((last-t0-(first or 0)) if last else 0,2),"approx_tok_s",round(n/max(0.01,(last-t0-first)) if first and last and last>t0+first else 0,2),"usage",u if 'u' in dir() else None)
except Exception as e: print("run $i ERR",e)
PY
done
echo "== gpu/cpu"; nvidia-smi --query-gpu=index,utilization.gpu --format=csv,noheader; uptime | a
echo "== threads/flags actually used"; ps -eo args | grep "[l]lama-server" | grep 8098 | tr ' ' '\n' | grep -E "^-(t|tb|b|ub|fa|ctk|ctv|ngl|c|np)$" -A1 | tr '\n' ' ' | a; echo
