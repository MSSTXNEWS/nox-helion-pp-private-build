echo "K1: o2_rec1"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
for p in nox_ops_core nox_runner_r01 nox_runners; do echo "CONF $p"; grep -hE "^(command|directory|environment)" /etc/supervisor/conf.d/$p.conf | cut -c1-220; done
supervisorctl status | grep -E "ops_core|runner" | awk '{print $1,$2,$4,$5}' | head -12
ls $N/mods | grep -iE "autonomy|board|bus|dispatch|receipt|hands" | tr '\n' ' '; echo
echo "autonomy.py:"; [ -f $N/mods/autonomy.py ] && (wc -l $N/mods/autonomy.py; grep -nE "^def |^class |^\"\"\"" $N/mods/autonomy.py | head -20) || echo absent
python3 -I - <<'PY'
import json,glob,os,collections,sqlite3,time
N="/workspace/nox"
def shp(v): return {k:(type(x).__name__ if isinstance(x,(dict,list)) else (x if isinstance(x,(int,float,bool)) or (isinstance(x,str) and len(x)<18) else "str")) for k,x in list(v.items())[:20]}
ts=glob.glob(N+"/state/tasks/*.json"); print("tasks",len(ts))
c=collections.Counter()
for p in ts:
    d=json.load(open(p,encoding="utf-8")); c[(d.get("source"),d.get("status"),d.get("user"))]+=1
print(dict(c)); d=json.load(open(ts[0],encoding="utf-8")); print("shape",shp(d)); print("stages",json.dumps(d.get("stages"),ensure_ascii=False)[:300])
print("task ages_h",sorted(round((time.time()-os.path.getmtime(p))/3600,1) for p in ts)[:12])
for f in glob.glob(N+"/state/agents/*.json")[:0]: pass
print("agents dir",sorted(os.listdir(N+"/state/agents"))[:40])
print("receipts",len(glob.glob(N+"/state/receipts/*")),sorted(os.listdir(N+"/state/receipts"))[-3:] if os.path.isdir(N+"/state/receipts") else None)
for p in glob.glob(N+"/state/**/*.sqlite*",recursive=True)+glob.glob(N+"/state/**/*.db",recursive=True):
    if "p3/eval" in p or p.endswith(("-wal","-shm")): continue
    try:
        cn=sqlite3.connect("file:%s?mode=ro"%p,uri=True,timeout=2); t=[r[0] for r in cn.execute("select name from sqlite_master where type='table'")][:8]; print("DB",os.path.relpath(p,N),os.path.getsize(p),t)
    except Exception as e: print("DB",os.path.relpath(p,N),"ERR",type(e).__name__)
PY
echo "== ops_core"; ls $N/ops 2>/dev/null | head -20 | tr '\n' ' '; echo
F=$(find $N -name 'nox_ops_core*' -not -path '*/archive/*' 2>/dev/null | head -3); echo "$F"
echo "== runner/dispatcher code defs"; for f in $(grep -rl "queued" $N/agent/nox_agents $N/ops 2>/dev/null --include=*.py | head -6); do echo "$f $(wc -l <$f)"; grep -nE "queued|def (claim|run_task|pick|poll|dispatch)" $f | head -6 | cut -c1-180; done
echo "== logs"; ls -t $N/logs | head -12 | tr '\n' ' '; echo
for f in $(ls -t $N/logs/*ops_core* $N/logs/*runner* 2>/dev/null | head -2); do echo "-- $f"; tail -4 $f | sed -E 's/[А-Яа-я]+/w/g' | cut -c1-200; done
echo "== agent modules"; ls $N/agent/nox_agents | tr '\n' ' '; echo
echo "== hands in orch"; ls $N/state/orch | head -20 | tr '\n' ' '; echo
echo END
