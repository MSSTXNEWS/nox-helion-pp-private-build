#!/bin/bash
echo GENOME:; find /root /opt -maxdepth 7 \( -iname 'genome_engine.py' -o -iname 'core_adapter.py' -o -iname 'GENOME' \) 2>/dev/null | head -4
echo CFG:; ls /root/nox/config | head -12 | tr '\n' ' '; grep -rhoE '^(export )?[A-Z_]*(KEY|TOKEN)[A-Z_]*=' /root/nox/config /root/nox/.env /root/.nox_env 2>/dev/null | sed 's/export //' | sort -u | tr '\n' ' '
echo; nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader | head -4
echo DB:; python3 -I - <<'PY'
import sqlite3
c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
for (n,s) in c.execute("select name,sql from sqlite_master where type='table' and name not like 'nox_mem_fts_%'"):
    k=c.execute('select count(*) from "%s"'%n).fetchone()[0]
    print(n,k,(s or '')[len(n)+14:230].replace('\n',' '))
PY
head -c 600 /root/nox/state/s03_copy_check.json; echo; ls -la --time-style=+%F /root/nox/memory/backups | tail -4 | cut -c20-120
