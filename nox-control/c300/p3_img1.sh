#!/bin/bash
N=/workspace/nox
echo "== gateway 8793 process/cache code"; P=$(ss -ltnp | grep ':8793 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "pid $P cwd=$(readlink /proc/$P/cwd) $(tr '\0' ' ' </proc/$P/cmdline | cut -c1-120)"
D=$(readlink /proc/$P/cwd); F=$(tr '\0' '\n' </proc/$P/cmdline | grep -E "\.py$" | head -1); echo "file $F"
grep -rn -i -E "cache|ttl|image|images/generations|pollinations|horde|seed|sha|hash" $D/$(basename $F) $F 2>/dev/null | grep -i -E "cache|image|seed|key" | cut -c1-200 | head -40
ls -la $N/state/advisor_images | tail -8
cat > /tmp/p3_imgtest.py <<'PY'
import sys,json,hashlib,time,base64,urllib.request
sys.path.insert(0,"/workspace/nox/ops/draw"); import invoke_draw as d
Q=["нарисуй кота в космосе","сделай фото красной машины на закате","нарисуй дракона над морем","нарисуй замок на горе зимой","draw a robot reading a book"]
out=open("/workspace/nox/state/p3/img_test.txt","w")
def w(*a): print(*a,file=out,flush=True)
for q in Q:
    pr=d.draw_request(q); w("Q",q,"->",pr, "photo",d.photo_request(q))
    try:
        r=d.local_generate(pr[1],None,d.photo_request(q))
        p=r["path"]; b=open(p,"rb").read(); w("  path",p,"sha",hashlib.sha256(b).hexdigest()[:12],"bytes",len(b),"src",r["source"],"s",r["seconds"])
        im="data:image/jpeg;base64,"+base64.b64encode(b).decode()
        body={"messages":[{"role":"user","content":[{"type":"text","text":"Describe in one short sentence what is in this image."},{"type":"image_url","image_url":{"url":im}}]}],"max_tokens":60,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}
        rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json"})
        t=time.time(); m=json.loads(urllib.request.urlopen(rq,timeout=300).read())["choices"][0]["message"]["content"]; w("  vision(%ds):"%(time.time()-t),m.strip()[:200])
    except Exception as e: w("  ERR",type(e).__name__,str(e)[:150])
w("DONE")
PY
nohup setsid /workspace/nox/venv/bin/python /tmp/p3_imgtest.py >/tmp/p3_imgtest.err 2>&1 &
echo "== direct gateway test: 2 prompts + repeat (cache check)"
for pr in "a red sports car at sunset, photo" "a cat in space, astronaut, stars" "a red sports car at sunset, photo"; do curl -s -m 100 -X POST 127.0.0.1:8793/v1/images/generations -H 'Content-Type: application/json' -d "{\"prompt\":\"$pr\",\"model\":\"auto\"}" | python3 -c "
import sys,json,hashlib
d=json.load(sys.stdin); x=d['data'][0]; p=x.get('path'); print('$pr','->',p, hashlib.sha256(open(p,'rb').read()).hexdigest()[:12] if p else '', d.get('model'), d.get('nox'))"; done
echo "== local /img/generate answer"; curl -s -m 30 -X POST 127.0.0.1:8091/img/generate -H 'Content-Type: application/json' -d '{"prompt":"cat","model":"auto"}' | head -c 200; echo
