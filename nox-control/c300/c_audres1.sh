echo "C300: c_audres1"
python3 - <<'PY'
import json
d=json.load(open("/workspace/nox/web/site/qa/audit.json")); c=d.get("chat") or {}
print("ts",c.get("ts")); print(json.dumps([(f.get("item","")[:50],str(f.get("detail"))[:160]) for f in c.get("fails",[])],ensure_ascii=False)[:1500]); print(str(c.get("vision_raw"))[:400])
PY
pgrep -fa "qa_audit.py chat" | cut -c1-80
