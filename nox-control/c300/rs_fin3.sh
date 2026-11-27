echo "K1: rs_fin3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; C=$N/web/pkg/server/chat_core.py
echo "--- 8144 who"; P=$(ss -ltnp | grep ':8144 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "pid=$P ni=$(ps -o ni= -p $P) ppid_cmd=$(ps -o args= -p $(ps -o ppid= -p $P) | cut -c1-90)"; tr '\0' ' ' </proc/$P/cmdline | sed -E 's/--api-key [^ ]+/--api-key ***/' | grep -oE "(-m [^ ]+|--port [0-9]+|-c [0-9]+|--parallel [0-9]+|-t [0-9]+)" | tr '\n' ' '; echo
echo "clients_established=$(ss -tnp state established '( sport = :8144 )' 2>/dev/null | grep -o 'users:((\"[^\"]*' | sort | uniq -c | tr '\n' ';')"
grep -rln "8144" $N/judges $N/web/pkg/server $N/agent/*.py $N/stewards 2>/dev/null | head -6
# 1) deep deadline + fillers
cp -a $C $C.bak_rsdl_$(date +%s)
python3 - <<'PY'
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
a="    def _l1_deadline():\n        time.sleep(45)\n"; assert s.count(a)==1
s=s.replace(a,"    def _l1_deadline():\n        time.sleep(90 if (mode == \"deep\" and not os.path.exists(\"/workspace/nox/state/deep_adv.off\")) else 45)   # RS: у deep 90 с\n")
b="    ex = cf.ThreadPoolExecutor(len(_DEEP_ADV)); fs = [ex.submit(one, m) for m in _DEEP_ADV]; res = []\n"; assert s.count(b)==1
s=s.replace(b,b+"    _fl = [True]\n    def _fill():\n        k = 0\n        while _fl[0] and k < 8:\n            time.sleep(3); k += 1\n            if _fl[0]: out({\"t\": \"stage\", \"text\": \"советники думают… %d с\" % (3 * k), \"code\": \"advisors_wait\"})\n    threading.Thread(target=_fill, daemon=True).start()\n")
c="    ex.shutdown(wait=False)\n    names = [m for m, _ in res]\n"; assert s.count(c)==1
s=s.replace(c,"    _fl[0] = False\n"+c)
s=s.replace("with ur.urlopen(rq, timeout=9) as r","with ur.urlopen(rq, timeout=16) as r").replace("cf.as_completed(fs, timeout=10)","cf.as_completed(fs, timeout=20)")
open(p,"w",encoding="utf-8").write(s)
PY
python3 -m py_compile $C && echo compile_ok || { cp -a $(ls -t $C.bak_rsdl_* | head -1) $C; echo REVERTED; }
# 2) owner_active: пауза 8144 на время хода
O=$N/stewards/owner_active.py; cp -a $O $O.bak_rs8144
python3 - <<'PY'
p="/workspace/nox/stewards/owner_active.py"; s=open(p,encoding="utf-8").read()
a='("llama8105", r"llama-server .*--port 8105 "),'; assert s.count(a)==1
open(p,"w",encoding="utf-8").write(s.replace(a,a+' ("llama8144", r"llama-server .*--port 8144 "),'))
PY
python3 -m py_compile $O && echo oa_compile_ok || cp -a $O.bak_rs8144 $O
supervisorctl restart nox_owner_active 2>&1 | tail -1; sleep 3; pgrep -f owner_active.py | wc -l
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 4; echo "health $(curl -s -m5 -o /dev/null -w %{http_code} http://127.0.0.1:18091/api/health)"
python3 - <<'PY'
import json,time,urllib.request,uuid
t0=time.time(); meta=[]; txt=0; fill=0
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-"+uuid.uuid4().hex[:6],"message":"Сравни плюсы и минусы Python и Rust для системного кода, кратко","mode":"deep"}).encode(),{"Content-Type":"application/json"}),timeout=130)
    for ln in r:
        try: o=json.loads(ln)
        except Exception: continue
        k=o.get("t")
        if k=="stage":
            if o.get("code")=="advisors_wait": fill+=1
            else: meta.append("stage:"+str(o.get("code")))
        if k=="meta" and o.get("advisors"): meta.append("advisors="+",".join(o["advisors"]))
        if k=="delta": txt+=len(o.get("text") or "")
        if k=="error": meta.append("ERROR:"+str(o.get("code")))
        if k=="done": meta.append("done_status=%s done_meta_adv=%s"%(o.get("status"),(o.get("meta") or {}).get("advisors"))); break
except Exception as e: meta.append("exc "+type(e).__name__)
print("DEEP sec=%.1f len=%d wait_events=%d %s"%(time.time()-t0,txt,fill,meta))
PY
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)") 2>&1 | grep -E "^(MEM_GET|ADDR|DRAW|IMG_FETCH|LOAD)" | sed -E 's/"events": \{[^}]*\}//;s/"(sec|done|error|len)": [^,}]*,? ?//g'
