#!/bin/bash
DB=$(tr '\0' '\n' < /proc/$(pgrep -f "python3 .*gateway.py" | head -1)/environ | grep '^NOX_MEMORY_DB=' | cut -d= -f2); echo "db=$DB"
python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]); c.row_factory=sqlite3.Row
for t in [r[0] for r in c.execute("select name from sqlite_master where type='table'")]:
    cols=[r[1] for r in c.execute(f"pragma table_info({t})")]
    if t.startswith('sqlite') or 'fts' in t: continue
    txt=[x for x in cols if x in('key','value','text','content','fact','body','title')]
    if not txt: continue
    q=" or ".join(f"{x} like '%Адриан%' or {x} like '%Марроу%'" for x in txt)
    rows=c.execute(f"select * from {t} where {q} limit 6").fetchall()
    print(t,len(rows))
    for r in rows: print("  ",{k:(str(r[k])[:90]) for k in r.keys() if k in ('id','key','section','value','text','source','status','conf','level')})
PY
echo "== glm"; pgrep -af "llama-server -m /root/nox/glm53" | cut -c1-120; curl -s -m 4 http://127.0.0.1:18098/health; echo; grep -vE "unused tensor" /root/nox/logs/glm_server.log | tail -3 | cut -c1-160; ls /root/nox/logs | head -20
