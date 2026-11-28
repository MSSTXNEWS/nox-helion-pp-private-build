echo "K1: s6l_b0"
# Личность: форма данных (маски), шифр паспорта и корпуса ответов на ключ потока 6, HF-доступ
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
P=$(mktemp); curl -fsSL $R/bundles/enc/s6_pub.pem -o $P
echo "## K1 inbox pub"; openssl pkey -in $N/state/keys/inbox.pem -pubout
python3 -I - <<'PY'
import json,os,re,glob,collections
def mask(s,n=100): return re.sub(r"\d","9",re.sub(r"[A-Za-zЀ-ӿ]","a",s))[:n]
N="/workspace/nox"
fs=glob.glob(N+"/state/web/web_conv/*.json"); print("web_conv files",len(fs),"bytes",sum(os.path.getsize(f) for f in fs))
f=max(fs,key=os.path.getsize); d=json.load(open(f,encoding="utf-8"))
print("biggest top type",type(d).__name__, list(d.keys())[:12] if isinstance(d,dict) else len(d))
def shape(o,dep=0):
    if isinstance(o,dict): return {k:shape(v,dep+1) for k,v in list(o.items())[:10]} if dep<3 else "dict"
    if isinstance(o,list): return [len(o),shape(o[0],dep+1) if o else None] if dep<3 else "list"
    return type(o).__name__
print(json.dumps(shape(d),ensure_ascii=False)[:600])
for p in ["state/core/recent_replies.jsonl","state/core/daymind/exemplars.jsonl","state/core/daymind/rethink_kto.jsonl","state/chat_pairs.qa","state/core/thoughts.jsonl"]:
    q=N+"/"+p
    if os.path.isfile(q):
        L=open(q,encoding="utf-8",errors="replace").read().splitlines(); 
        try: r=json.loads(L[-1]); print(p,len(L),json.dumps(shape(r),ensure_ascii=False)[:300])
        except Exception: print(p,len(L),"nonjson")
    else: print(p,"absent")
PY
echo "## HF reach"; curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 https://huggingface.co/api/datasets/HuggingFaceH4/ultrafeedback_binarized
echo "## passport enc"
F=$N/state/core/passport.json; W=$(mktemp -d); openssl rand -out $W/k 32
openssl enc -aes-256-cbc -pbkdf2 -salt -in $F -out $W/a.enc -pass file:$W/k
echo "EK $(openssl pkeyutl -encrypt -pubin -inkey $P -in $W/k | base64 -w0)"
echo "ED_BEGIN"; base64 -w0 $W/a.enc; echo; echo "ED_END"
rm -rf $W $P; echo END
