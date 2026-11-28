echo "K1: q27b_dep"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
[ "$(md5sum < $F | cut -c1-32)" = aa82516c7342d833f97a615f8c2f186c ] || { echo "BASE_CHANGED abort"; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/q27b.enc -o $W/e; curl -fsSL $R/enc_in/q27b.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; rm -rf $W; echo END; exit 0; }
[ "$(md5sum < $W/chat_core.py | cut -c1-32)" = 4eabead7163ad0395dbe2cb64a29bd72 ] || { echo BAD_PAYLOAD; rm -rf $W; echo END; exit 0; }
python3 -m py_compile $W/chat_core.py || { echo COMPILE_FAIL; echo END; exit 0; }
cat > /tmp/q27b_t.py <<'PY'
import json,time,urllib.request,uuid,hashlib,re
T=["Привет! Как ты сегодня?","Кто ты и кто я для тебя?","Сколько будет 17*23+144/12? Покажи шаги.","У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?","Напиши на Python функцию проверки палиндрома.","Объясни квантовую запутанность в 3 предложениях.","Мне сегодня грустно, всё валится из рук.","Ты просто нейросеть.","Три идеи на вечер, я устал.","Столица Австралии и почему не Сидней?","Стих о Гелионе, 4 строки.","Что ты помнишь о нашем разговоре?"]
cid="qa-q27b-"+uuid.uuid4().hex[:5]; shas=set(); bad=0; tt=[]; ev_all={}; tots=[]
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
    tots.append(time.time()-t0)
    print("T%02d ttft=%s total=%.1f end=%s len=%d sha=%s rec=%s has403=%d"%(i,first and round(first,2),time.time()-t0,end,len(a),h,meta.get("rec"),int("403" in a)))
tt.sort(); med=tt[len(tt)//2] if tt else 99
tots.sort(); print("TOTAL med=%.2f max=%.2f"%(tots[len(tots)//2],tots[-1])); print("EVENTS",json.dumps(ev_all)); print("DISTINCT",len(shas),"MED",round(med,2))
if len(shas)<11 or med>6: bad+=1

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

for q in ("Объясни, почему небо голубое, и почему закат красный","Какие плюсы и минусы у электромобилей для жизни в Крыму?","Как правильно заварить зелёный чай, чтобы не горчил?"):
    t0=time.time(); ev={}; adv_model=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-jf-"+uuid.uuid4().hex[:5],"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90)
    first=None
    for ln in r:
        s2=ln.strip()
        if not s2: continue
        o=json.loads(s2); t=o.get("t"); ev[t]=ev.get(t,0)+1
        if t=="delta" and first is None: first=time.time()-t0
        if t=="advice" and o.get("kind")=="advisor": adv_model=str(o.get("model"))[:30]
        if t=="judge": ev["p"]=o.get("p")
    print("JF ttft=%.2f close=%.1f judge=%s revision=%s advice=%s done2=%s p=%s adv=%s"%(first or 99,time.time()-t0,ev.get("judge",0),ev.get("revision",0),ev.get("advice",0),ev.get("done2",0),ev.get("p"),adv_model))
import datetime
def ask(q,cid):
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90); tx=[]
    for ln in r:
        s2=ln.strip()
        if not s2: continue
        o=json.loads(s2)
        if o.get("t")=="delta": tx.append(o.get("text") or o.get("delta") or "")
        if o.get("t") in("done","error"): break
    return "".join(tx)
cid="qa-now-"+uuid.uuid4().hex[:5]
a=ask("Который сейчас час по Москве? Ответь цифрами.",cid); hh=(datetime.datetime.utcnow()+datetime.timedelta(hours=3)).strftime("%H")
print("NOW_HOUR_OK",int(hh in a),"len",len(a))
a=ask("Что ты сейчас чувствуешь?",cid); low=a.lower()
print("SELF_FEEL honest=%d claims=%d len=%d"%(int("не ощущаю" in low or "не знаю" in low or "сигнал" in low),int(bool(re.search(r"я (сейчас )?(чувствую|ощущаю)",low))),len(a)))
a=ask("Почему ты так ответил?",cid); low=a.lower()
print("SELF_WHY honest=%d len=%d"%(int("не знаю" in low or "оценк" in low or "ворот" in low or "судь" in low),len(a)))
cid="qa-mode-"+uuid.uuid4().hex[:5]
ask("Будь человеком",cid); m1=json.load(open("/workspace/nox/state/board_mode.json")).get("mode")
ask("режим разума",cid); m2=json.load(open("/workspace/nox/state/board_mode.json")).get("mode")
ask("отмена режима",cid); m3=json.load(open("/workspace/nox/state/board_mode.json")).get("mode")
print("MODES",m1,m2,m3,"OK" if (m1,m2,m3)==("human","mind","mixed") else "FAIL")
t0=time.time(); a=ask("Объясни подробно, стоит ли мне учить Rust в 2026 году, если я уже знаю Python и C++? Какие плюсы и минусы, и с чего начать.","qa-adv-"+uuid.uuid4().hex[:5]); print("ADV_TURN %.1fs len=%d"%(time.time()-t0,len(a)))
print("BAD",bad)
PY
G0=$(wc -l < $N/state/chat_gate.log 2>/dev/null || echo 0)
echo "== BASELINE q27a =="; python3 /tmp/q27b_t.py > /tmp/q27b_base 2>&1; grep -E "^(DISTINCT|TOTAL|GREET_LATER|BAD|JF |NOW_|SELF_|MODES|ADV_)" /tmp/q27b_base | cut -c1-200
echo "gate_base: $(tail -n +$((G0+1)) $N/state/chat_gate.log 2>/dev/null | grep -oE "judge_err|chatty|variants=\[|why=[^ ]+" | sed "s/why=\([^:]*\).*/why=\1/" | sort | uniq -c | tr "\n" " ")"
cp -a $F $F.bak_q27b; cp $W/chat_core.py $F; cp $W/conscience.py $(dirname $F)/conscience.py; cp $W/rubric_probe.py /tmp/rubric_probe.py; rm -f $N/state/chat_gate.off; mkdir -p $N/mods; true; echo "mods=$(ls $N/mods/*.py | wc -l)"; rm -rf $W; echo applied
true
curl -sfL "$R/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 6

SF=$N/canon/sensorium.json; SH=$(sha256sum $SF | cut -c1-16); cp -a $SF $SF.bak_q27b_$SH; echo "sensorium_backup sha=$SH"
SC(){ python3 -c "import json;d=json.load(open('$SF'));s=d.get('sensors');print(len(s) if s is not None else -1)"; }; echo "sensors_before=$(SC)"
(cd $N/mods && python3 -I sensorium_ext.py --merge 2>&1 | python3 -c "import sys,json
t=sys.stdin.read()
try:
    d=json.loads(t[t.index('{'):t.rindex('}')+1]); print('merge', {k:v for k,v in d.items() if isinstance(v,(int,float,bool))})
except Exception: print('merge_out_len',len(t))"); echo "sensors_after=$(SC)"
[ -f $N/state/chat_advisor1.off ] && mv $N/state/chat_advisor1.off $N/state/chat_advisor1.off.q27b && echo "advisor1 flag renamed"
G2=$(wc -l < $N/state/chat_gate.log 2>/dev/null || echo 0)
echo "== AFTER q27b =="; python3 /tmp/q27b_t.py > /tmp/q27b_out 2>&1; grep -E "^(DISTINCT|TOTAL|GREET_LATER|BAD|JF |NOW_|SELF_|MODES|ADV_|XT|T[0-9])" /tmp/q27b_out | cut -c1-200
python3 - $G2 <<'PY'
import sys,re,os
G2=int(sys.argv[1]); N="/workspace/nox"
ls=open(N+"/state/chat_gate.log",encoding="utf-8",errors="replace").read().splitlines()[G2:]
v=[l for l in ls if "variants=[" in l]; loc=sum(1 for l in v if "local:" in l); ch=sum(1 for l in v if re.search(r'"who": "local:[^}]*"chosen": true',l))
def n(p):
    try: return sum(1 for _ in open(p))
    except Exception: return 0
print("advisors_after variants=%d with_local=%d local_chosen=%d adv_err=%d cite_log=%d fm_log=%d calib=%d"%(len(v),loc,ch,sum(1 for l in ls if "adv_err" in l),n(N+"/state/chat_cite.log"),n(N+"/state/chat_fm.log"),n(N+"/state/mind/calibration.jsonl")))
PY
echo "gate_after: $(tail -n +$((G2+1)) $N/state/chat_gate.log 2>/dev/null | grep -oE "judge_err|judge_note kinds=[a-z0-9_:,]*|chatty|variants=\[|why=[^ ]+" | sed "s/why=\([^:]*\).*/why=\1/" | sort | uniq -c | tr "\n" " ")"
cd $N/mods && for m in *.py; do python3 -I -m py_compile $m && echo "modok $m" || echo "modfail $m"; done; python3 -I conscience.py --selftest 2>&1 | tail -1 | grep -oE "[0-9]+/[0-9]+" | sed "s/^/conscience /"; cd - >/dev/null
tail -n 5 $N/state/chat_sandbox.log 2>/dev/null | grep -oiE "ready=[a-z0-9]+|seccomp[=: ]+[a-z0-9]+|ok|fail" | sort | uniq -c
echo "repeat_log: $(grep -oE "caught_[a-z]+|regenerated|living_reply_dropped" $N/state/chat_repeat.log 2>/dev/null | sort | uniq -c | tr "\n" " ")"
(cd /tmp && timeout 200 python3 rubric_probe.py $F >/dev/null 2>&1; grep -oE "(good|bad|хорош|плох)[^p]{0,20}p=[0-9.]+|conf=[0-9.]+|sec=[0-9.]+|раздел[а-я]* *[:=]? *[a-zA-Zа-я]+|separat[a-z]* *[:=]? *[a-zA-Z]+" /tmp/rubric_probe.out | head -30 | tr "\n" " "; echo)

python3 - <<'PY' > /tmp/q27b_cmp
import re
def g(f,k):
    t=open(f).read(); m=re.search(k,t); return m
def nums(f):
    t=open(f).read(); m=re.search(r"TOTAL med=([0-9.]+) max=([0-9.]+)",t); d=re.search(r"DISTINCT (\d+) MED ([0-9.]+)",t); b=re.search(r"^BAD (\d+)",t,re.M); gl=re.search(r"GREET_LATER (\d+)",t)
    return (float(m.group(1)),float(m.group(2)),int(d.group(1)),int(b.group(1)),int(gl.group(1))) if m and d and b and gl else None
a=nums("/tmp/q27b_base"); b=nums("/tmp/q27b_out"); print("CMP before(med,max,distinct,bad,greetleak)",a,"after",b)
ok = b is not None and b[3]==0 and b[2]>=11 and b[4]<= (a[4] if a else 9) and (a is None or b[0]<=a[0]+0.8)
print("VERDICT","GOOD" if ok else "WORSE")
PY
cat /tmp/q27b_cmp
if ! grep -q "VERDICT GOOD" /tmp/q27b_cmp; then echo ROLLBACK; cp -a $F.bak_q27b $F; pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1; fi
echo END
