echo "C300: srv_k154"
python3 - <<'PY'
import json,time,http.client
sysm="Ты NOX, тёплый ассистент. "*25
for name,msgs,mt in (("короткий",[{"role":"user","content":"Привет, NOX! Как дела?"}],300),("system700",[{"role":"system","content":sysm[:700]},{"role":"user","content":"Привет, NOX! Как дела?"}],300)):
    body={"model":"x","messages":msgs,"stream":True,"max_tokens":mt,"temperature":0.7,"chat_template_kwargs":{"enable_thinking":False}}
    t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",8104,timeout=30)
    c.request("POST","/v1/chat/completions",body=json.dumps(body,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    r=c.getresponse(); hd=time.time()-t0; first=None; n=0
    while True:
        l=r.readline()
        if not l: break
        if l.startswith(b"data:") and b'"content"' in l and b'"content":""' not in l:
            n+=1
            if first is None: first=time.time()-t0
        if n>=8: break
    print(name,"заголовки %.2f первый токен %s"%(hd, None if first is None else round(first,2)))
PY
curl -s -m4 http://127.0.0.1:8104/slots | python3 -c "import sys,json; print([(s['id'],s.get('is_processing'),s.get('n_ctx')) for s in json.load(sys.stdin)])"
tail -n 3 /workspace/nox/state/chat_fast.log
