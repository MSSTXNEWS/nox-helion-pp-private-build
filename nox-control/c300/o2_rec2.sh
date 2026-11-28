echo "K1: o2_rec2"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
ls $N/agent/nox_ops | tr '\n' ' '; echo; wc -l $N/agent/nox_ops/ops_core.py
grep -nE "tasks|queued|state/tasks|def " $N/agent/nox_ops/ops_core.py | head -40 | cut -c1-170
echo "-- log tail"; tail -5 $N/agent/out/nox_ops_core.log | sed -E 's/[А-Яа-я]+/w/g' | cut -c1-220
echo "-- who reads/writes state/tasks"; grep -rlE "state/tasks|/tasks/" $N/agent $N/web/pkg/server $N/mods --include=*.py 2>/dev/null | head -8
python3 -I - <<'PY'
import sqlite3,json,glob,os,time,collections
N="/workspace/nox"
cn=sqlite3.connect("file:"+N+"/state/bus/events.db?mode=ro",uri=True,timeout=3)
for t in ("events","board"):
    print(t,[ (r[1],r[2]) for r in cn.execute("pragma table_info(%s)"%t)])
print("jmode",cn.execute("pragma journal_mode").fetchone(),"events n",cn.execute("select count(*) from events").fetchone(),"board n",cn.execute("select count(*) from board").fetchone())
cols=[r[1] for r in cn.execute("pragma table_info(events)")]
kc=[c for c in cols if c in("kind","type","topic","name","t")]
if kc: print("kinds",cn.execute("select %s,count(*) from events group by 1 order by 2 desc limit 15"%kc[0]).fetchall())
print("last row keys/types",[(c,type(v).__name__) for c,v in zip(cols,cn.execute("select * from events order by rowid desc limit 1").fetchone())])
print("board sample",[ (type(v).__name__) for v in (cn.execute("select * from board limit 1").fetchone() or [])])
print("wal",os.path.exists(N+"/state/bus/events.db-wal"))
c=collections.Counter()
for p in glob.glob(N+"/state/tasks/*.json"):
    d=json.load(open(p,encoding="utf-8")); c[(str(d.get("cid"))[:3], d.get("title","")[:28] if str(d.get("cid")).startswith("qa-") else "(real)")]+=1
print("task kinds",dict(c))
PY
echo END
