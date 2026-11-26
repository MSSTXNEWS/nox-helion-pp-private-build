echo "C300: srv_k7"
cd /workspace/nox/agents
grep -n "quota" nox_worms.py | cut -c1-260 | head
./venv/bin/python - <<'PY'
import sqlite3
c=sqlite3.connect('worms.sqlite')
print(c.execute("select sql from sqlite_master where name='quota'").fetchall())
print(c.execute("select * from quota order by rowid desc limit 5").fetchall())
print(c.execute("select src,count(*),max(ts) from finds group by src").fetchall())
PY
ls | grep -E "\.sh$|run|start" | head; grep -rn "nox_agents" /workspace/nox/ops/*.sh /workspace/nox/agent/*.sh 2>/dev/null | head -4
