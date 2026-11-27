echo "K1: l1_ttft1"
grep "первый токен" /workspace/nox/state/chat_fast.log | tail -8 | awk '{print $3}' | tr '\n' ' '; echo
S=/workspace/nox/state/pipe_err.log; echo "pipe_err_lines=$(wc -l < $S 2>/dev/null)"
for i in 1 2 3; do python3 - <<'P'
import json,time,urllib.request
t0=time.time()
for url,body in (("http://127.0.0.1:8104/v1/chat/completions",{"model":"x","messages":[{"role":"user","content":"Привет"}],"max_tokens":8,"stream":True,"id_slot":0,"cache_prompt":True,"chat_template_kwargs":{"enable_thinking":False}}),):
  rq=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
  with urllib.request.urlopen(rq,timeout=60) as r:
    for l in r:
      if l.startswith(b"data:") and b"content" in l: print("direct_ttft",round(time.time()-t0,2)); break
P
done
echo "load1=$(cut -d' ' -f1 /proc/loadavg)"; ps -eo pcpu,comm --sort=-pcpu | head -6 | awk '{print $1,$2}' | tr '\n' ';'
