#!/bin/bash
# b_audit_read.sh: чтение вердиктов qa/audit.json (мои разделы и A) и структуры data/live.json (без изменений)
set -u
S=/workspace/nox/web/site
python3 - "$S" <<'PY'
import sys, json
S=sys.argv[1]
a=json.load(open(S+"/qa/audit.json",encoding="utf-8"))
print("audit keys:", list(a)[:30])
for k in ["voice","cinema","music","news","studio","photo","chat","index","consciousness","organism","training","selffeel"]:
    v=a.get(k)
    if v is None: print(k,"-> NO ENTRY"); continue
    fails=v.get("fails",[]) if isinstance(v,dict) else []
    print(k, "verdict=",(v.get("verdict") if isinstance(v,dict) else v), "ts=",(v.get("ts") if isinstance(v,dict) else ""), "fails=",len(fails))
    for f in fails[:6]: print("   -", f.get("item","")[:90], "|", str(f.get("detail",""))[:140])
PY
echo "== live.json"
python3 -c "
import json
d=json.load(open('$S/data/live.json',encoding='utf-8'))
print(type(d).__name__, list(d)[:25] if isinstance(d,dict) else len(d))
" 2>&1 | head -5
