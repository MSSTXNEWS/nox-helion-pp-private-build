echo "K1: rs_dbg"
export RUNNER_TRACKING_ID=""
cat /proc/loadavg; ps -eo pcpu,ni,args --sort=-pcpu | head -6 | cut -c1-110
python3 - <<'PY'
import json,time,urllib.request,uuid,concurrent.futures as cf
def one(m):
    t=time.time()
    try:
        rq=urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",data=json.dumps({"model":m,"messages":[{"role":"user","content":"Сравни Python и Rust кратко"}],"max_tokens":350,"temperature":0.4}).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(rq,timeout=20) as r: j=json.loads(r.read())
        c=(((j.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        return m,"%.1fs"%(time.time()-t),len(c)
    except Exception as e: return m,"%.1fs"%(time.time()-t),type(e).__name__+str(e)[:60]
ms=["groq/llama-3.3-70b-versatile","cerebras/qwen-3-32b","google/gemini-2.5-flash","llm7/deepseek-v4.1-flash"]
with cf.ThreadPoolExecutor(4) as ex: print("ADV",list(ex.map(one,ms)))
t0=time.time(); ev=[]
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":"Нарисуй кота","mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=100)
for ln in r:
    try: o=json.loads(ln)
    except Exception: continue
    ev.append((o.get("t"),o.get("stage") or o.get("code"),round(time.time()-t0,1), {k:(str(v)[:60] if k in("path","url","image","src","media") else None) for k,v in o.items() if k in("path","url","image","src","media")}))
    if o.get("t") in("done","error"): break
print("DRAWEV",[e for e in ev if e[0]!="delta"][:12], "deltas",sum(1 for e in ev if e[0]=="delta"))
PY
tail -5 /workspace/nox/state/pipe_err.log 2>/dev/null | cut -c1-200
