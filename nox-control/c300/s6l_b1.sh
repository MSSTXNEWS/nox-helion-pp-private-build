echo "K1: s6l_b1"
# Личность: корпус ответов NOX шифрованно на ключ потока 6 (тексты в открытый лог не выводятся)
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
P=$(mktemp); curl -fsSL $R/bundles/enc/s6_pub.pem -o $P
W=$(mktemp -d)
python3 -I - $W <<'PY'
import json,glob,sys,os,collections
W=sys.argv[1]; N="/workspace/nox"; out=open(W+"/corpus.jsonl","w",encoding="utf-8"); n=collections.Counter()
for f in glob.glob(N+"/state/web/web_conv/*.json"):
    try: d=json.load(open(f,encoding="utf-8"))
    except Exception: continue
    ms=d.get("messages") or []; last_user=None
    for m in ms:
        r=m.get("role"); t=m.get("content") or ""
        if r=="user": last_user=t
        elif r in ("assistant","nox") and t.strip():
            out.write(json.dumps({"cid":d.get("id"),"ts":m.get("ts"),"src":m.get("source"),"user":last_user,"answer":t},ensure_ascii=False)+"\n"); n["conv"]+=1
for l in open(N+"/state/core/recent_replies.jsonl",encoding="utf-8",errors="replace"):
    try: r=json.loads(l)
    except Exception: continue
    out.write(json.dumps({"cid":"recent","ts":r.get("ts"),"src":"recent","user":None,"answer":r.get("text","")},ensure_ascii=False)+"\n"); n["recent"]+=1
out.close(); print("rows",dict(n))
PY
cp $N/state/chat_gate.log $W/chat_gate.log; cp $N/state/chat_judge.log $W/chat_judge.log
tar czf $W/a.tgz -C $W corpus.jsonl chat_gate.log chat_judge.log; echo "tgz_bytes=$(stat -c %s $W/a.tgz)"
openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/a.tgz -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
