echo "C300: srv_k156"
python3 - <<'PY'
import json,time,http.client
sysm=("Ты NOX, тёплый ассистент. Отвечай по-русски, по делу. "*20)[:600]
def run(user,slot=0):
    body={"model":"x","messages":[{"role":"system","content":sysm},{"role":"user","content":user}],"stream":True,"max_tokens":8,"temperature":0.7,"cache_prompt":True,"chat_template_kwargs":{"enable_thinking":False}}
    if slot is not None: body["id_slot"]=slot
    t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",8104,timeout=60)
    c.request("POST","/v1/chat/completions",body=json.dumps(body,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    r=c.getresponse(); first=None
    while True:
        l=r.readline()
        if not l: break
        if l.startswith(b"data:") and b'"content"' in l and b'"content":""' not in l: first=round(time.time()-t0,2); break
    return first
print("slot0 холодный", run("Привет"))
print("slot0 тот же префикс, другой вопрос", run("Как дела сегодня?"))
print("slot0 ещё", run("Что нового?"))
print("без id_slot", run("Расскажи анекдот"))
PY
curl -s -m4 http://127.0.0.1:8104/slots | python3 -c "import sys,json; print([(s['id'],s.get('is_processing')) for s in json.load(sys.stdin)])"
tail -n 3 /workspace/nox/web/restart_k1.log | cut -c1-200
