echo "K1: q27_gw"
export RUNNER_TRACKING_ID=""
D=/workspace/nox/advisors; G=$D/gateway.py
mask(){ sed -E 's/(gsk_|AIza|csk-|sk-|nvapi-|hf_)[A-Za-z0-9_-]{6,}/KEY/g' | cut -c1-210; }
echo "--- cfg"; python3 - <<'PY'
import json,os
D="/workspace/nox/advisors"
for f in sorted(os.listdir(D)):
    if f.endswith(".json") and "cfg" in f or f=="advisors_cfg.json":
        try: d=json.load(open(D+"/"+f))
        except Exception as e: print(f,"bad"); continue
        def walk(o,p=""):
            if isinstance(o,dict):
                for k,v in o.items():
                    if isinstance(v,(dict,list)): walk(v,p+k+".")
                    else:
                        kl=k.lower(); sec=any(x in kl for x in ("key","token","secret","pass"))
                        print(f,p+k,("SET" if v else "EMPTY") if sec else str(v)[:60])
            elif isinstance(o,list): print(f,p,"list",len(o),[str(x)[:40] for x in o[:6]] if not any(isinstance(x,dict) for x in o) else "dicts")
        walk(d)
PY
echo "--- key sources in code"; grep -nE "environ|\.key|_KEY|keys/|api_key|load_key|def key" $G | mask | head -25
echo "--- fallback/lcoder"; grep -nE "lcoder|fallback|local" $G | mask | head -20
echo "--- provider table"; grep -nE "PROV|base_url|https://" $G | mask | head -20
echo "--- private rule"; sed -n 186,200p $G | mask
echo "--- key files presence"; for p in groq cerebras gemini google openrouter kilo llm7 nvidia mistral; do f=$(ls /workspace/nox/state/keys 2>/dev/null | grep -i $p | head -1); echo "$p keyfile=$([ -n "$f" ] && echo yes || echo no) env_in_gw=$(tr '\0' '\n' < /proc/$(ss -ltnp | grep '127.0.0.1:8793 ' | sed 's/.*pid=\([0-9]*\).*/\1/')/environ | grep -ciE "^${p}[a-z_]*key=.+")"; done
echo "--- gateway live status"; curl -s -m 5 http://127.0.0.1:8793/health | head -c 400; echo
curl -s -m 8 http://127.0.0.1:8793/v1/models | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];import collections;print(len(d),dict(collections.Counter(x['id'].split('/')[0] for x in d)))" 2>&1 | cut -c1-300
echo "--- direct net reach (code only)"; for h in api.groq.com api.cerebras.ai generativelanguage.googleapis.com openrouter.ai api.mistral.ai api.kilo.ai api.llm7.io integrate.api.nvidia.com; do echo "$h $(curl -s -m 8 -o /dev/null -w '%{http_code} %{time_total}s' https://$h/ 2>&1)"; done
echo "--- via gateway per model"; python3 - <<'PY'
import json,time,urllib.request,urllib.error
def call(m,msg,pri="chat"):
    b={"model":m,"messages":[{"role":"user","content":msg}],"max_tokens":40,"temperature":0}
    t=time.time()
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json","X-NOX-Priority":pri}),timeout=25).read()); c=d["choices"][0]["message"].get("content") or ""
        return "ok %.2fs reply_model=%s ans=%s"%(time.time()-t,str(d.get("model"))[:34],"yes" if "париж" in c.lower() or "paris" in c.lower() else "no")
    except urllib.error.HTTPError as e:
        b2=e.read().decode("utf-8","replace"); return "http%d %.2fs %s"%(e.code,time.time()-t,b2[:70].replace("\n"," "))
    except Exception as e: return type(e).__name__
for m in ("groq/llama-3.3-70b-versatile","cerebras/qwen-3-32b","google/gemini-2.5-flash","openrouter/auto","kilo/kilo-auto/free","llm7/Inkling-Small","auto"):
    print(m,call(m,"Столица Франции? Одним словом."))
print("judge-like",call("groq/llama-3.3-70b-versatile","Вопрос: Столица Австралии?\n\nОтвет для оценки: Канберра. Верни JSON {p_good}."))
PY
echo END
