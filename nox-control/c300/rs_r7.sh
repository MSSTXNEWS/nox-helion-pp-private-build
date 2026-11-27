echo "K1: rs_r7"
export RUNNER_TRACKING_ID=""
W=/workspace/nox; C=$W/web/pkg/server/chat_core.py
sed -n 331,372p $W/judges/judge_service.py | cut -c1-240
echo "--- rte payload"; sed -n 768,782p $C | cut -c1-300
echo "--- judges"; curl -s -m5 http://127.0.0.1:8300/judges | cut -c1-600
echo "--- models test (без ключей; если шлюз требует ключ — отметка AUTH)"
python3 - <<'PY'
import json,urllib.request,time,concurrent.futures as cf
U="http://127.0.0.1:8793"
def call(m):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(U+"/v1/chat/completions",json.dumps({"model":m,"messages":[{"role":"user","content":"Ответь одним словом: да"}],"max_tokens":16}).encode(),{"Content-Type":"application/json"}),timeout=25)
        j=json.loads(r.read()); msg=((j.get("choices") or [{}])[0].get("message") or {}); ok=bool(msg.get("content") or msg.get("reasoning_content")); return m,r.status,round(time.time()-t,1),"da" if ok else "empty"
    except urllib.error.HTTPError as e: return m,e.code,round(time.time()-t,1),"AUTH" if e.code==401 else "NET"
    except Exception as e: return m,type(e).__name__,round(time.time()-t,1),"NET"
ms=[x["id"] for x in json.loads(urllib.request.urlopen(U+"/v1/models",timeout=6).read())["data"]]
with cf.ThreadPoolExecutor(8) as ex: res=list(ex.map(call,ms))
print("n_models",len(ms))
for r in res: print("MODEL | %s | %s | %ss | %s"%r)
print("OK_COUNT",sum(1 for r in res if r[3]=="da"))
PY
