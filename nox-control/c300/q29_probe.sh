echo "K1: q29_probe"
export RUNNER_TRACKING_ID=""
python3 - <<'PY'
import json,time,urllib.request,urllib.error
def call(port,model="x",extra=None,to=20):
    b={"model":model,"messages":[{"role":"system","content":"Ты NOX. Отвечай коротко."},{"role":"user","content":"Что такое радуга? Одним предложением."}],"max_tokens":60,"temperature":0.4}
    if extra: b.update(extra)
    t=time.time()
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions"%port,json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=to).read())
        c=d["choices"][0]["message"].get("content"); rc=d["choices"][0]["message"].get("reasoning_content")
        return "ok %.2fs content_len=%s reasoning_len=%s finish=%s"%(time.time()-t,len(c or ""),len(rc or ""),d["choices"][0].get("finish_reason"))
    except urllib.error.HTTPError as e: return "http%d %.2fs %s"%(e.code,time.time()-t,e.read()[:80].decode("utf-8","replace").replace("\n"," "))
    except Exception as e: return "%s %.2fs"%(type(e).__name__,time.time()-t)
for port in (8142,8141,8152,8151,8104):
    print(port,"plain",call(port))
    print(port,"nothink",call(port,extra={"chat_template_kwargs":{"enable_thinking":False}}))
PY
for p in 8142 8141 8152 8151; do echo "$p props: $(curl -s -m 4 http://127.0.0.1:$p/props | python3 -c "import sys,json;d=json.load(sys.stdin);print('slots',d.get('total_slots'),'model',str(d.get('model_alias') or d.get('model_path'))[-40:])" 2>&1 | cut -c1-120)"; done
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -1
echo END
