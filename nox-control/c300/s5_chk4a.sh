python3 - <<'P'
import json,os
Q="/workspace/nox/web/site/qa/"
a=json.load(open(Q+"audit.json"))
for k in ("index","chat","calendar","events","nav","settings","system"):
    v=a.get(k,{}); f=Q+"rework/%s.json"%k
    j=json.load(open(f)) if os.path.exists(f) else {}
    print("ST",k,v.get("status"),v.get("wow"),v.get("ARU"),v.get("cycle"),v.get("ts","")[11:16],"s5=",("s5_review" in j))
    if k in("index","nav","settings"): print("  FAILS",[ (x['item'][:40],str(x['detail'])[:120]) for x in v.get("fails",[])][:4])
P
ls /workspace/nox/web/site/qa/rework/*.fixed 2>/dev/null; date +%H:%M
