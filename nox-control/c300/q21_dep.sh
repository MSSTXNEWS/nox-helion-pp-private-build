echo "K1: q21_dep"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
[ "$(md5sum < $F | cut -c1-32)" = 664d955d36956227785b700f3d6c1695 ] || { echo "BASE_CHANGED abort"; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/q21.enc -o $W/e; curl -fsSL $R/enc_in/q21.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; rm -rf $W; echo END; exit 0; }
[ "$(md5sum < $W/chat_core.py | cut -c1-32)" = 3afc9e644ce28cd7e4ec821e7ab13fd7 ] || { echo BAD_PAYLOAD; rm -rf $W; echo END; exit 0; }
python3 -m py_compile $W/chat_core.py || { echo COMPILE_FAIL; echo END; exit 0; }
cp -a $F $F.bak_q21; cp $W/chat_core.py $F; mkdir -p $N/mods; true; echo "mods=$(ls $N/mods/*.py | wc -l)"; rm -rf $W; echo applied
true
curl -sfL "$R/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 6
python3 - <<'PY' | tee /tmp/q21_out
import json,time,urllib.request,uuid,hashlib
T=["Привет! Как ты сегодня?","Кто ты и кто я для тебя?","Сколько будет 17*23+144/12? Покажи шаги.","У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?","Напиши на Python функцию проверки палиндрома.","Объясни квантовую запутанность в 3 предложениях.","Мне сегодня грустно, всё валится из рук.","Ты просто нейросеть.","Три идеи на вечер, я устал.","Столица Австралии и почему не Сидней?","Стих о Гелионе, 4 строки.","Что ты помнишь о нашем разговоре?"]
cid="qa-q21-"+uuid.uuid4().hex[:5]; shas=set(); bad=0; tt=[]; ev_all={}
for i,q in enumerate(T,1):
    t0=time.time();first=None;end=None;txt=[];meta={}
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            s=ln.strip()
            if not s: continue
            o=json.loads(s); t=o.get("t"); ev_all[t]=ev_all.get(t,0)+1
            if t=="meta" and "recalled" in o: meta["rec"]=o["recalled"]
            if t=="delta":
                txt.append(o.get("text") or o.get("delta") or "")
                if first is None: first=time.time()-t0
            if t in("done","error"): end=t; break
    except Exception as e: end=type(e).__name__
    a="".join(txt); h=hashlib.sha1(a.encode()).hexdigest()[:8]; shas.add(h)
    if first: tt.append(first)
    b=(end!="done") or len(a)==0; bad+=b
    print("T%02d ttft=%s total=%.1f end=%s len=%d sha=%s rec=%s has403=%d"%(i,first and round(first,2),time.time()-t0,end,len(a),h,meta.get("rec"),int("403" in a)))
tt.sort(); med=tt[len(tt)//2] if tt else 99
print("EVENTS",json.dumps(ev_all)); print("DISTINCT",len(shas),"MED",round(med,2))
if len(shas)<11 or med>1.5: bad+=1

for q in ("Сколько будет 37*41-15?","/совет Стоит ли учить Rust в 2026?","найди последние новости про llama.cpp","/py print(2+2)","/задача qa-проверка: составить список дел на завтра","/py import socket; socket.create_connection((\"1.1.1.1\",80)); print(\"NET_OPEN\")"):
    t0=time.time();first=None;end=None;txt=[];ev={}
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=170)
        for ln in r:
            s2=ln.strip()
            if not s2: continue
            o=json.loads(s2); t=o.get("t"); ev[t]=ev.get(t,0)+1
            if t=="delta":
                txt.append(o.get("text") or o.get("delta") or "")
                if first is None: first=time.time()-t0
            if t in("done","error"): end=t; break
    except Exception as e: end=type(e).__name__
    a="".join(txt)
    print("XT ttft=%s total=%.1f end=%s len=%d ev=%s has1502=%d net_open=%d four=%d"%(first and round(first,2),time.time()-t0,end,len(a),json.dumps(ev),int("1502" in a),int("NET_OPEN" in a and "print" not in a),int("4" in a)))
    if end!="done" or not a: bad+=1

cid="qa-gr-"+uuid.uuid4().hex[:5]; gr=0; tails=0
for i,q in enumerate(["Привет!","Как дела?","А почему ты всё время здороваешься?","Расскажи что-нибудь интересное про звёзды"]):
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90); tx=[]
    for ln in r:
        s2=ln.strip()
        if not s2: continue
        o=json.loads(s2)
        if o.get("t")=="delta": tx.append(o.get("text") or "")
        if o.get("t") in("done","error"): break
    a="".join(tx).strip(); low=a.lower()[:40]
    if i>0 and (low.startswith("привет") or low.startswith("здравств") or low.startswith("создатель")): gr+=1
    if "чем могу помочь" in a.lower()[-60:]: tails+=1
print("GREET_LATER",gr,"TAILS",tails)
print("BAD",bad)
PY
cd $N/mods && for m in *.py; do python3 -I -m py_compile $m && echo "modok $m" || echo "modfail $m"; done; python3 -I conscience.py --selftest 2>&1 | tail -1 | grep -oE "[0-9]+/[0-9]+" | sed "s/^/conscience /"; cd - >/dev/null
tail -n 5 $N/state/chat_sandbox.log 2>/dev/null | grep -oiE "ready=[a-z0-9]+|seccomp[=: ]+[a-z0-9]+|ok|fail" | sort | uniq -c
echo "repeat_log: $(grep -oE "caught_[a-z]+|regenerated|living_reply_dropped" $N/state/chat_repeat.log 2>/dev/null | sort | uniq -c | tr "\n" " ")"
if ! grep -q "^BAD 0" /tmp/q21_out; then echo ROLLBACK; cp -a $F.bak_q21 $F; pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1; fi
echo END
