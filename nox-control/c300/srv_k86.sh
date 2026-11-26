echo "C300: srv_k86"
cat > /tmp/k85.py <<'PY'
import json,time,urllib.request,sys
def run(url,q,stream=True):
    b=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":60,"stream":stream,"chat_template_kwargs":{"enable_thinking":False}}).encode(); t0=time.time(); ft=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,data=b,headers={"Content-Type":"application/json"}),timeout=40)
        for l in r:
            if l.startswith(b'data: {'):
                if ft is None: ft=time.time()-t0
                n+=1
            elif not stream and ft is None and l.strip(): ft=time.time()-t0
    except Exception as e: return ("err",repr(e)[:50])
    return (round(ft or -1,2), round(time.time()-t0,2), n)
qs=["Привет! Как дела?","Столица Канады?","Сколько будет 15*15?","Кто написал Преступление и наказание?","Сколько часов в сутках?"]
for name,url in (("8104 прямо","http://127.0.0.1:8104/v1/chat/completions"),("8510 цепочка","http://127.0.0.1:8510/v1/chat/completions"),("8400 каскад","http://127.0.0.1:8400/v1/chat/completions")):
    print(name,[run(url,q) for q in qs],flush=True)
PY
/workspace/nox/venv/bin/python -I /tmp/k85.py
