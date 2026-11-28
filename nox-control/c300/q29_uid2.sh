echo "K1: q29_uid2"
export RUNNER_TRACKING_ID=""
python3 - <<'PY'
import glob,json,os,time,collections
c=collections.Counter()
for f in glob.glob("/workspace/nox/state/web/**/*.json",recursive=True):
    try:
        if time.time()-os.path.getmtime(f)>3*86400: continue
        d=json.load(open(f))
    except Exception: continue
    if not isinstance(d,dict) or "messages" not in d: continue
    qa=str(d.get("id","")).startswith(("qa-","rv-"))
    u=str(d.get("user") or "")
    c[("qa" if qa else "real", u if u in ("","owner","dima","guest") else "other")]+=1
print(dict(c))
PY
grep -c "user_id" /workspace/nox/web/site/nox-chat*.js 2>/dev/null | head -3
grep -lE "user_id" /workspace/nox/web/site/*.js 2>/dev/null | head -3 | sed 's#.*/##'
echo END
