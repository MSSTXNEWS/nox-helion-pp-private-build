echo "C300: c_probe9"
N=/workspace/nox
python3 - <<'PY'
import json,urllib.request,threading,time
def post(m,t=16):
    t0=time.time()
    try:
        rq=urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",data=json.dumps({"model":m,"messages":[{"role":"user","content":"Столица Франции? Одно слово."}],"max_tokens":20}).encode(),headers={"Content-Type":"application/json"})
        r=json.loads(urllib.request.urlopen(rq,timeout=t).read()); return (m,"ok",int((time.time()-t0)*1000),(r["choices"][0]["message"]["content"] or "")[:30].replace("\n"," "),r.get("model"))
    except Exception as e: return (m,"fail",int((time.time()-t0)*1000),str(e)[:50],None)
d=json.load(urllib.request.urlopen("http://127.0.0.1:8793/v1/models",timeout=5))["data"]
ids=[m["id"] for m in d]; print("models:",len(ids)); 
for m in d: print(" ",m["id"],m.get("status"),m.get("latency_ms"),"avail",m.get("available"),"key",m.get("needs_key"))
out=[]; th=[threading.Thread(target=lambda m=m: out.append(post(m))) for m in ids+["auto"]]
[t.start() for t in th]; [t.join(20) for t in th]
for o in sorted(out,key=lambda x:(x[1]!="ok",x[2])): print(o)
PY
echo "== сбой черновика"
ps aux | grep -E "nox_core|8090" | grep -v grep | cut -c1-200 | head -3
for F in $N/tmp/liska_alive/nox_core.py $N/tmp/liska_alive/pipeline.py; do echo "--- $F"; grep -n -B8 -A2 "сбой черновика" $F | cut -c1-200 | head -30; done
ls $N/core 2>/dev/null | head; grep -rln "сбой черновика" $N/core $N/organs $N/svc/core 2>/dev/null | head -3
