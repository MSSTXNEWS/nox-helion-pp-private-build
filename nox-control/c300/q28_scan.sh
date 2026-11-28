echo "K1: q28_scan"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "md5 chat_core $(md5sum < $N/web/pkg/server/chat_core.py | cut -c1-32)"
grep -rlE "не сложился|сбой черновика" $N --include=*.py --include=*.js --include=*.json 2>/dev/null | grep -vE "\.bak|/out/|node_modules|state/" | sed "s#$N/##" | head
for f in $(grep -rlE "не сложился|сбой черновика" $N --include=*.py 2>/dev/null | grep -vE "\.bak|/out/|node_modules|state/" | head -3); do echo "== $f"; grep -nE "не сложился|сбой черновика" $f | cut -c1-260 | head -5; done
echo "counts in conv store (numbers only):"
python3 - <<'PY'
import glob,json,re,collections
c=collections.Counter(); tot=0
pats={"nesl":re.compile(r"не сложился|сбой черновика"),"slow":re.compile(r"отвечаю медленно"),"messir":re.compile(r"(?i)\bмессир"),"creator":re.compile(r"(?i)\bсоздател")}
for f in glob.glob("/workspace/nox/state/core_conv_*.json"):
    try: d=json.load(open(f))
    except Exception: continue
    for m in d.get("messages",[]):
        if m.get("role")!="assistant": continue
        a=str(m.get("content") or ""); tot+=1
        for k,r in pats.items():
            if r.search(a): c[k]+=1
print("assistant_msgs",tot,dict(c))
PY
echo "passport keys: $(python3 -c "import json;d=json.load(open('$N/state/core/passport.json'));print(sorted(d))")"
python3 -c "
import json;d=json.load(open('$N/state/core/passport.json'));ad=d.get('addressing',{});print('addressing keys',sorted(ad));print('creator list',ad.get('creator'));o=(ad.get('users') or {}).get('owner');print('owner',o if not isinstance(o,dict) else {k:v for k,v in o.items() if k in('main_form','forms','rotation')})" 2>&1 | cut -c1-400
echo "persona_prefix:"; grep -nE "def _persona_prefix|def _passport" $N/web/pkg/server/chat_core.py | head; grep -n "self_report" $N/web/pkg/server/*.py | cut -c1-140 | head -5
echo END
