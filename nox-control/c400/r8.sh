#!/bin/bash
find /root/nox/backup_s2/unpacked /root/nox/backup_s03_pre_p401 /root/nox/pkg -xdev \( -iname '*s03*.sqlite*' -o -iname 'canonical.sqlite' -o -iname 's03*.db' \) -size +1M -printf '%s %p\n' 2>/dev/null | sort -rn | head -12 | cut -c1-150
python3 -I - <<'PY'
import sqlite3,glob
for p in glob.glob('/root/nox/backup_s2/unpacked/**/canonical.sqlite',recursive=True)[:4]+glob.glob('/root/nox/backup_s2/unpacked/**/reboot-snapshots/*/s03.sqlite',recursive=True)[:2]:
    try:
        c=sqlite3.connect('file:%s?mode=ro'%p,uri=True)
        print(p[-70:],[(n,c.execute('select count(*) from "%s"'%n).fetchone()[0]) for (n,) in c.execute("select name from sqlite_master where type='table' and name not like '%fts%'") ][:10])
    except Exception as e: print(p[-50:],e)
PY
