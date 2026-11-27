echo "K1: rs_t3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 5; echo "health $(curl -s -m5 -o /dev/null -w %{http_code} http://127.0.0.1:18091/api/health)"
python3 - <<'PY'
import json,time,urllib.request,uuid
def turn(mode,msg,cid=None,extra=None):
    t0=time.time(); ev=[]; meta=[]; txt=0
    try:
        b={"conversation_id":cid or "rv-"+uuid.uuid4().hex[:6],"message":msg,"mode":mode}; b.update(extra or {})
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=100)
        for ln in r:
            try: o=json.loads(ln)
            except Exception: continue
            k=o.get("t"); ev.append(k)
            if k=="stage": meta.append("stage:"+str(o.get("code")))
            if k=="meta" and o.get("advisors"): meta.append("advisors="+",".join(o["advisors"]))
            if k=="delta": txt+=len(o.get("text") or "")
            if k=="done": meta.append("done_meta_adv=%s"%((o.get("meta") or {}).get("advisors"))); break
    except Exception as e: return "DEEP exc %s"%type(e).__name__
    return "TURN %s sec=%.1f len=%d %s"%(mode,time.time()-t0,txt,meta)
print(turn("deep","Сравни плюсы и минусы Python и Rust для системного кода, кратко"))
print(turn("fast","Столица Франции?"))
def post(u,b,to=20):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=to); d=r.read(); return "%s %.1fs %s"%(r.status,time.time()-t,d[:160].decode("utf8","replace") if False else len(d))
    except urllib.error.HTTPError as e: return "%s %.1fs"%(e.code,time.time()-t)
    except Exception as e: return "%s %.1fs"%(type(e).__name__,time.time()-t)
print("JUDGE_FAST",post("http://127.0.0.1:8300/judge",{"text":"Столица Франции Париж.","context":"Столица Франции?","fast":True,"role":"answer"},30))
print("RTE_TURN",post("http://127.0.0.1:8084/v1/turns?stream=1&compat=openai",{"conversation_id":"rv-rte","client_msg_id":"rv-rte-1","message":"Привет","mode":"fast","source":"web","length":"short","history":[],"self_speech":None},60))
PY
echo "--- draft GET"; curl -s -m10 -o /dev/null -w "DRAFT %{http_code} %{time_total}\n" "http://127.0.0.1:18091/svc/advisors/draft?typed=%D1%80%D0%B0%D1%81%D1%81%D0%BA%D0%B0%D0%B6%D0%B8%20%D0%BC%D0%BD%D0%B5%20%D0%BF%D1%80%D0%BE%20%D1%81%D0%BE%D0%BB%D0%BD%D1%86%D0%B5&chat=rv-x"
curl -s -m10 "http://127.0.0.1:18091/svc/advisors/draft?typed=%D1%80%D0%B0%D1%81%D1%81%D0%BA%D0%B0%D0%B6%D0%B8%20%D0%BC%D0%BD%D0%B5%20%D0%BF%D1%80%D0%BE%20%D1%81%D0%BE%D0%BB%D0%BD%D1%86%D0%B5&chat=rv-x" | python3 -c "import sys,json;j=json.load(sys.stdin);print('draft keys',{k:(len(v) if isinstance(v,str) else v) for k,v in j.items()})" 2>&1 | cut -c1-200
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)") 2>&1 | grep -E "^(MEM_GET|ADDR|JM|DRAW|IMG_FETCH|LOAD)" | sed -E 's/"events": \{[^}]*\}//'
