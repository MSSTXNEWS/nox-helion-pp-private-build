echo "K1: m10_probe1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/svc/mem; DB=$N/state/core/s03.db
df -BG / | tail -1 | awk '{print "disk_free_G="$4}'
md5sum $D/nox_mem.py $D/nox_rerank.py | awk '{print $1, $2}'
ls -la $D | awk '{print $5,$9}' | head -20
supervisorctl status nox_mem nox_rerank 2>&1 | head -3
curl -s -m 3 127.0.0.1:18220/health; echo
ss -ltn | grep -E ":8082 |:8083 |:18220 " | awk '{print $4}'
$N/venv_mem/bin/python -I - <<'PY'
import sqlite3,sqlite_vec,os
c=sqlite3.connect("file:/workspace/nox/state/core/s03.db?mode=ro",uri=True); c.enable_load_extension(True); sqlite_vec.load(c)
for n,t,sql in c.execute("select name,type,sql from sqlite_master order by type,name"):
    try: cnt=c.execute('select count(*) from "%s"'%n).fetchone()[0] if t=="table" else ""
    except Exception as e: cnt="err"
    print(t,n,cnt,(sql or "").replace("\n"," ")[:220])
print("size",os.path.getsize("/workspace/nox/state/core/s03.db"))
for q in ["select source, count(*) from s03 group by substr(source,1,6) limit 12","select owner,count(*) from s03 group by owner","select min(ts),max(ts) from s03","select status,count(*) from s03_mem group by status"]:
    try: print(q[:40],c.execute(q).fetchall())
    except Exception as e: print("ERR",q[:30],e)
PY
echo "## pip (venv_mem)"; $N/venv_mem/bin/pip list 2>/dev/null | grep -i -E "graphiti|kuzu|neo4j|falkor|sqlite|mem0|numpy|sentence|torch|onnx|rank|fastembed|flag" 
echo "## models"; ls -d $N/models/*bge* $N/models/*rerank* 2>/dev/null; find $N -maxdepth 4 -iname "*bge*" -not -path "*/venv*" 2>/dev/null | head -8
ps aux | grep -E "8082|8083|bge|rerank|embed" | grep -v grep | awk '{print $11,$12,$13,$14,$15,$16,$17,$18}' | cut -c1-200 | head
echo "## recall log"; wc -l $N/state/s03_recall.log; awk '{for(i=1;i<=NF;i++) if($i ~ /^hits=/){split($i,a,"=");h[a[2]]++}} END{for(k in h) print "hits="k, h[k]}' $N/state/s03_recall.log
grep -c "" $N/state/s03_recall.off 2>/dev/null; ls $N/state | grep -i -E "qa|recall|s03|mem" | head
ls $N/state/core | head -40
echo END
