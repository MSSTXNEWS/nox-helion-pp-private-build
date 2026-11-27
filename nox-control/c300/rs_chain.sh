echo "K1: rs_chain"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
p(){ # name url [method] [body]
  local o; if [ -n "$4" ]; then o=$(curl -s -m 12 -o /dev/null -w "%{http_code} %{time_total}" -X "$3" -H 'Content-Type: application/json' -d "$4" "$2"); else o=$(curl -s -m 8 -o /dev/null -w "%{http_code} %{time_total}" "$2"); fi
  c=${o%% *}; case "$c" in 2*) ok=da;; *) ok=NET;; esac; echo "CHAIN $1 | $2 | $o | $ok"; }
for pt in 8793 18217 8300 8810 18218 8084 8083 8090 8200 8104 18220 8097 8796; do echo "LISTEN $pt $(ss -ltn | grep -c ":$pt ")"; done
for pt in 8793 18217 8300 8810 18218 8084 8083 8090 8200; do for pa in /health /healthz /v1/models /status /; do p "p$pt" http://127.0.0.1:$pt$pa; done; done
p advisors_draft_gate http://127.0.0.1:18091/svc/advisors/draft POST '{"text":"привет","q":"привет"}'
p advisors_svc http://127.0.0.1:18091/svc/advisors/health
p fast http://127.0.0.1:18217/fast POST '{"q":"2+2","message":"2+2"}'
grep -nE "8083|8084" $N/web/pkg/server/*.py $N/ops/*/*.json $N/ops/*/*.yaml 2>/dev/null | cut -c1-160 | head -8
python3 - <<'PY'
import json,time,urllib.request,uuid
def turn(mode,msg):
    t0=time.time(); ev={}; adv=0; txt=0; keys=set()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-"+uuid.uuid4().hex[:6],"message":msg,"mode":mode}).encode(),{"Content-Type":"application/json"}),timeout=170)
        for ln in r:
            try: o=json.loads(ln)
            except Exception: continue
            k=str(o.get("t") or o.get("type") or o.get("event")); ev[k]=ev.get(k,0)+1
            s=json.dumps(o,ensure_ascii=False).lower()
            if "advis" in s or "советник" in s: adv+=1; keys.add(k)
            if k in("delta","d","text","token"): txt+=len(str(o.get("delta") or o.get("text") or o.get("d") or ""))
            if k in("done","error"): break
    except Exception as e: return "TURN %s exc=%s sec=%.1f"%(mode,type(e).__name__,time.time()-t0)
    return "TURN %s sec=%.1f len=%d adv_events=%d adv_kinds=%s events=%s"%(mode,time.time()-t0,txt,adv,sorted(keys),ev)
print(turn("deep","Объясни в двух предложениях, почему небо голубое"))
print(turn("fast","Столица Франции?"))
PY
