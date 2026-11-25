echo "C300: c_audfix1"
S=/workspace/nox/web/site/qa
python3 - <<'PY'
import json,shutil
S="/workspace/nox/web/site/qa/"
cur=json.load(open(S+"audit.json")); old=json.load(open(S+"audit.json.bak_c_1"))
c1=(old.get("chat") or {}); c0=(cur.get("chat") or {})
print("cur chat ts",c0.get("ts"),"| bak_c_1 chat ts",c1.get("ts"))
if str(c1.get("ts",""))>str(c0.get("ts","")):
    cur["chat"]=c1; json.dump(cur,open(S+"audit.json.tmp","w"),ensure_ascii=False); json.load(open(S+"audit.json.tmp")); shutil.move(S+"audit.json.tmp",S+"audit.json"); print("merged newer chat entry")
PY
echo "== loop"; cat /workspace/nox/qa_audit_loop.sh | head -30 | cut -c1-200
