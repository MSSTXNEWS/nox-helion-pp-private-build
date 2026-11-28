echo "K1: q27_gw2"
export RUNNER_TRACKING_ID=""
G=/workspace/nox/advisors/gateway.py
mask(){ sed -E 's/(gsk_|AIza|csk-|sk-|nvapi-|hf_)[A-Za-z0-9_-]{6,}/KEY/g' | cut -c1-260; }
echo "--- keys()"; sed -n 40,60p $G | mask
echo "--- PRIVATE_TOPICS"; grep -n "PRIVATE_TOPICS *=" $G | mask
echo "--- 4210"; ss -ltn | grep -c ":4210 "; curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4210/kilo/v1/models; curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4210/llm7/v1/models
python3 - <<'PY'
import json,time,urllib.request,urllib.error
def call(m,msg,extra=None):
    b={"model":m,"messages":[{"role":"user","content":msg}],"max_tokens":60,"temperature":0}
    if extra: b.update(extra)
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json","X-NOX-Priority":"chat"}),timeout=40).read())
        n=d.get("nox") or {}; return "reply_model=%s nox=%s"%(str(d.get("model"))[:30],json.dumps({k:(v if not isinstance(v,str) else v[:60]) for k,v in n.items() if k in("provider","local","tried","label","redacted","ms")},ensure_ascii=False)[:300])
    except urllib.error.HTTPError as e: return "http%d %s"%(e.code,e.read().decode("utf-8","replace")[:90])
    except Exception as e: return type(e).__name__
print("keyless",call("kilo/kilo-auto/free","Столица Франции?"))
print("llm7",call("llm7/Inkling-Small","Столица Франции?"))
print("local_only_flag",call("auto","Столица Франции?",{"x_nox_prio":9}))
for t in ("Вопрос: Столица Австралии?\n\nОтвет для оценки: Канберра.","Ответ для оценки: Канберра.","Оцени ответ: Канберра.","Ответ: Канберра. p_good","Столица Австралии?"):
    r=call("groq/llama-3.3-70b-versatile",t); print("probe",repr(t[:28]),"BLOCK403" if r.startswith("http403") else r[:40])
PY
echo END
