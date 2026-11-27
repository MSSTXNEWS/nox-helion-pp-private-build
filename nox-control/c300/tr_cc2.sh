export RUNNER_TRACKING_ID=""
echo "C300: tr_cc2"
F=/workspace/nox/web/pkg/server/chat_core.py
echo "#### 284-298"; sed -n 284,298p $F | cut -c1-300
echo "#### 367-452"; sed -n 367,452p $F | cut -c1-330
echo "#### 512-530"; sed -n 512,530p $F | cut -c1-260
echo "#### 555-612"; sed -n 555,612p $F | cut -c1-260
echo "#### passport keys"; python3 - <<'PY'
import json
d=json.load(open("/workspace/nox/state/core/passport.json"))
def walk(o,p="",n=0):
    if isinstance(o,dict):
        for k,v in o.items():
            if any(x in k.lower() for x in ("обращ","титул","title","address","creator","создат","owner","call","name","user")): print(p+k,"=",str(v)[:120].replace("\n"," "))
            if n<2: walk(v,p+k+".",n+1)
walk(d); print("top",list(d)[:20])
PY
echo "#### chat_fast.log"; tail -25 /workspace/nox/state/chat_fast.log | cut -c1-200
ls /workspace/nox/state/*owner* 2>/dev/null | head -4
echo END
