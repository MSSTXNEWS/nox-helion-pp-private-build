#!/bin/bash
DB=$(tr '\0' '\n' < /proc/$(pgrep -f "python3 .*gateway.py" | head -1)/environ | grep '^NOX_MEMORY_DB=' | cut -d= -f2)
cp "$DB" "$DB.bak_name" 2>/dev/null
python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1],timeout=30)
n=c.execute("update mem_profile set status='rejected' where value like '%Адриан%' or value like '%Марроу%'").rowcount
tabs=[r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("profile rejected",n,tabs)
for t in tabs:
    cols=[r[1] for r in c.execute(f"pragma table_info({t})")]
    if 'text' in cols and not t.startswith('sqlite') and 'fts' not in t:
        try:
            k=c.execute(f"delete from {t} where text like '%Адриан%' or text like '%Марроу%'").rowcount; print(t,"deleted",k)
        except Exception as e: print(t,"err",e)
c.commit()
PY
echo "== glm error"; grep -E " E |error|failed|alloc|CUDA" /root/nox/logs/glm_server.log | grep -v unused | tail -8 | cut -c1-220
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
free -g | head -2; pgrep -af llama-server | cut -c1-200
