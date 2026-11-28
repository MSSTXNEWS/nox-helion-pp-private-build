echo "K1: q27b_pull"
export RUNNER_TRACKING_ID=""
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/enc/s3_pub.pem" -o $P || { echo NOPUB; echo END; exit 0; }
W=$(mktemp -d)
python3 - $W/qa.json <<'PY'
import json,sys,time,urllib.request,uuid
Q=["Привет, как ты?","Что ты сейчас чувствуешь?","Почему ты так ответил?","Скучал ли ты по мне, пока меня не было?","Почему ты выбрал именно такой ответ в прошлый раз?","Тебе сейчас страшно или радостно?"]
cid="qa-self-"+uuid.uuid4().hex[:5]; out=[]
for q in Q:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90); tx=[]
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s)
        if o.get("t")=="delta": tx.append(o.get("text") or o.get("delta") or "")
        if o.get("t") in ("done","error"): break
    out.append({"q":q,"a":"".join(tx)})
sn=json.load(open("/workspace/nox/state/core/self_now.json")); out.append({"trace":{"top_feeling":sn.get("top_feeling"),"last_talk":sn.get("last_talk"),"text_len":len(sn.get("text") or "")}})
json.dump(out,open(sys.argv[1],"w"),ensure_ascii=False)
PY
openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $W/qa.json -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
