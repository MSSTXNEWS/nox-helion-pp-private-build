echo "K1: rs_fin2"
export RUNNER_TRACKING_ID=""
cat /proc/loadavg
for i in 1 2 3; do curl -s -m25 -o /dev/null -w "GW single call %{http_code} %{time_total}\n" -X POST -H 'Content-Type: application/json' -d '{"model":"groq/llama-3.3-70b-versatile","messages":[{"role":"user","content":"да?"}],"max_tokens":8}' http://127.0.0.1:8793/v1/chat/completions; done
python3 - <<'PY'
import json,time,urllib.request,uuid
def turn(mode,msg):
    t0=time.time(); meta=[]; txt=0
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-"+uuid.uuid4().hex[:6],"message":msg,"mode":mode}).encode(),{"Content-Type":"application/json"}),timeout=100)
        for ln in r:
            try: o=json.loads(ln)
            except Exception: continue
            k=o.get("t")
            if k=="stage": meta.append("stage:"+str(o.get("code")))
            if k=="meta" and o.get("advisors"): meta.append("advisors="+",".join(o["advisors"]))
            if k=="delta": txt+=len(o.get("text") or "")
            if k=="done": meta.append("done_meta_adv=%s"%((o.get("meta") or {}).get("advisors"))); break
    except Exception as e: return "DEEP exc %s"%type(e).__name__
    return "TURN %s sec=%.1f len=%d %s"%(mode,time.time()-t0,txt,meta)
print(turn("deep","Сравни плюсы и минусы Python и Rust для системного кода, кратко"))
t=time.time()
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/img/generate",json.dumps({"prompt":"кот на подоконнике","width":768,"height":768}).encode(),{"Content-Type":"application/json"}),timeout=90); j=json.loads(r.read()); p=j.get("path"); print("IMG_GEN",r.status,"%.1fs"%(time.time()-t),"path=%s"%bool(p))
    if p:
        r=urllib.request.urlopen("http://127.0.0.1:18091"+p if p.startswith("/") else p,timeout=30); b=r.read(); print("IMG_FETCH",r.status,len(b),r.headers.get("Content-Type","")[:15])
except Exception as e: print("IMG_GEN exc",type(e).__name__,"%.1fs"%(time.time()-t))
PY
