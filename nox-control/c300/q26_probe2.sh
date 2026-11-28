echo "K1: q26_probe2"
export RUNNER_TRACKING_ID=""
python3 - <<'PY'
import json,time,urllib.request,urllib.error,re
H={"Content-Type":"application/json","X-NOX-Priority":"chat"}
def call(m,pri="chat",extra=None):
    b={"model":m,"messages":[{"role":"user","content":"Ответь одним словом: столица Франции?"}],"max_tokens":20,"temperature":0}
    if extra: b.update(extra)
    h=dict(H); h["X-NOX-Priority"]=pri; t=time.time()
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",json.dumps(b).encode(),h),timeout=15).read()); return "ok %.2f model=%s"%(time.time()-t,str(d.get("model"))[:30])
    except urllib.error.HTTPError as e:
        body=e.read()[:400].decode("utf-8","replace"); low=body.lower()
        tags=[w for w in ("key","quota","limit","country","region","blocked","forbidden","model","priority","budget","disabled","rate","auth","token","cloudflare","html") if w in low]
        return "http%d %.2f len%d tags=%s"%(e.code,time.time()-t,len(body),tags)
    except Exception as e: return type(e).__name__
for m in ("cerebras/qwen-3-32b","groq/llama-3.3-70b-versatile","google/gemini-2.5-flash","groq/llama-3.1-8b-instant"):
    for pri in ("chat","bg"): print(m,pri,call(m,pri))
print("jsonobj",call("groq/llama-3.3-70b-versatile","chat",{"response_format":{"type":"json_object"}}))
try:
    d=json.loads(urllib.request.urlopen("http://127.0.0.1:8793/v1/models",timeout=5).read()); print("models",len(d.get("data",[])),[x.get("id")[:30] for x in d.get("data",[])][:12])
except Exception as e: print("models",type(e).__name__)
for p in ("/health","/status","/stats"):
    try: print(p,urllib.request.urlopen("http://127.0.0.1:8793"+p,timeout=5).read()[:300].decode("utf-8","replace").replace("\n"," ")[:300])
    except Exception as e: print(p,type(e).__name__)
PY
echo END
