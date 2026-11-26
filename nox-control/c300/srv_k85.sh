echo "C300: srv_k85"
cat > /tmp/k85.py <<'PY'
import json,time,urllib.request,sys
def run(url,q,stream=True):
    b=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":60,"stream":stream,"chat_template_kwargs":{"enable_thinking":False}}).encode(); t0=time.time(); ft=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,data=b,headers={"Content-Type":"application/json"}),timeout=120)
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
echo == cascade
curl -s -m5 http://127.0.0.1:8400/health | head -c 300; echo
ls /workspace/nox/cascade 2>/dev/null | head; tail -n 6 /workspace/nox/state/cascade_verdicts.jsonl 2>/dev/null | cut -c1-300
echo == draw
cd /workspace/nox/ops/draw; /workspace/nox/venv/bin/python -I - <<'PY'
import sys,json,time,base64,urllib.request
sys.path.insert(0,'.'); import invoke_draw as D
t0=time.time(); dr=D.draw_request("нарисуй кота в космосе")
try:
    r=D.local_generate(dr[1] if dr else "кот в космосе", photographic=False); print("draw",r.get("source"),r.get("seconds"),r.get("path"))
    b=base64.b64encode(open(r["path"],"rb").read()).decode()
    body={"model":"x","max_tokens":60,"temperature":0,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}},{"type":"text","text":"Does this image clearly show a cat in outer space? Answer YES or NO first, then one short sentence."}]}]}
    v=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=200))["choices"][0]["message"]["content"]; print("vision",v[:120])
except Exception as e: print("draw err",repr(e)[:200], "%.0f c"%(time.time()-t0))
PY
