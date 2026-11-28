echo "K1: dg11 (read-only code view)"; N=/workspace/nox; V=$N/distill_v2
sed -n 1564,1610p $V/code/distill_v2.py | cut -c1-210
echo "--- hold_frozen.json keys"; python3 -c "
import json;d=json.load(open('$N/state/hold_frozen.json'));print({k:(v if isinstance(v,(int,float,bool)) or (isinstance(v,str) and len(v)<60) else type(v).__name__) for k,v in d.items()})"
echo "--- builders of v1 (maxsim_train)"; grep -rlE "maxsim_train" $N/ops $V/code 2>/dev/null | head -5 | sed 's#/workspace/nox/##'
echo "--- hold_extra.json keys"; python3 -c "
import json;d=json.load(open('$V/hold_extra.json'));print(type(d).__name__, list(d)[:8] if isinstance(d,dict) else len(d))"
echo "--- split/kind/group/mode distribution of v1"; python3 - <<'PY'
import json,collections
rows=[json.loads(l) for l in open("/workspace/nox/distill_v2/hold_frozen_v1.jsonl",encoding="utf-8") if l.strip()]
for k in ("split","kind","group","mode"): print(k,collections.Counter(str(r.get(k)) for r in rows).most_common(8))
print("maxsim_train max/mean",max(r["maxsim_train"] for r in rows if isinstance(r.get("maxsim_train"),(int,float))), round(sum(r["maxsim_train"] for r in rows if isinstance(r.get("maxsim_train"),(int,float)))/len(rows),3))
PY
echo END
