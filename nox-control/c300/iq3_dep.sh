echo "K1: iq3_dep"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
[ "$(md5sum < $F | cut -c1-32)" = 1a6fe6f4abad3fd4af79604824f230aa ] || { echo "BASE_CHANGED abort"; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/iq3.enc -o $W/e; curl -fsSL $R/enc_in/iq3.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; rm -rf $W; echo END; exit 0; }
[ "$(md5sum < $W/chat_core.py | cut -c1-32)" = 54e69094b7687ebed2e222a2577280ad ] || { echo BAD_PAYLOAD; rm -rf $W; echo END; exit 0; }
python3 -m py_compile $W/chat_core.py || { echo COMPILE_FAIL; echo END; exit 0; }
cp -a $F $F.bak_iq3; cp $W/chat_core.py $F; rm -rf $W; echo applied
curl -sfL "$R/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 6
python3 - <<'PY' | tee /tmp/iq3_out
import json,time,urllib.request,uuid
bad=0
for q in ("привет","Сколько будет 17*23+144/12?","У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?","Мне сегодня грустно, всё валится из рук."):
    t0=time.time();first=None;end=None;txt=[]
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            s=ln.strip()
            if not s: continue
            o=json.loads(s); t=o.get("t")
            if t=="delta":
                txt.append(o.get("text") or o.get("delta") or "")
                if first is None: first=time.time()-t0
            if t in("done","error"): end=t; break
    except Exception as e: end=type(e).__name__
    a="".join(txt); th=int("<think" in a or "</think" in a)
    print("TURN ttft",None if first is None else round(first,2),"total",round(time.time()-t0,1),"end",end,"len",len(a),"think_leak",th,"has403",int("403" in a),"has6",int("6" in a))
    bad+= (end!="done") or th or len(a)==0 or (first or 99)>8
print("BAD",bad)
PY
if ! grep -q "^BAD 0" /tmp/iq3_out; then echo ROLLBACK; cp -a $F.bak_iq3 $F; pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1; fi
echo END
