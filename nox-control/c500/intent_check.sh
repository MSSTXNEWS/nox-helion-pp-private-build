#!/usr/bin/env bash
# c500: бэкап S03, проверка nox_intent на КОПИИ реального S03 (живая база не меняется). Ничего не перезапускает.
exec 9>/tmp/srv.lock; flock 9
set -u
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/wow7/brain
DB="${S03_DB:-/root/nox/memory/s03.db}"; W=/tmp/c500; mkdir -p $W/code /root/nox/memory/backups
[ -f "$DB" ] || { echo "НЕТ $DB"; ls /root/nox/memory /root/nox/state 2>&1 | head; exit 1; }
TS=$(date +%Y%m%d_%H%M%S); BK=/root/nox/memory/backups/s03_pre_intent_$TS.sqlite
python3 - "$DB" "$BK" <<'PY'
import sqlite3,sys
s=sqlite3.connect(sys.argv[1],timeout=20); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()
PY
echo "backup: $BK $(stat -c %s $BK) байт sha=$(sha256sum $BK | cut -c1-12)"
python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect("file:%s?mode=ro"%sys.argv[1],uri=True)
for (t,) in c.execute("select name from sqlite_master where type='table' order by 1"):
    try: print(t, c.execute("select count(*) from %s"%t).fetchone()[0], [r[1] for r in c.execute("pragma table_info(%s)"%t)][:8])
    except Exception as e: print(t,"err",e)
PY
for f in nox_intent.py test_intent.py; do curl -fsSL $R/$f -o $W/code/$f || { echo "не скачался $f"; exit 1; }; done
cp "$BK" $W/copy.sqlite
NOX_INTENT_TEST_DB=$W/copy.sqlite python3 $W/code/test_intent.py 2>&1 | tail -18
python3 - "$DB" <<'PY'
import sqlite3,sys
c=sqlite3.connect("file:%s?mode=ro"%sys.argv[1],uri=True)
print("живая БД: intent_* таблиц =", c.execute("select count(*) from sqlite_master where name like 'intent_%'").fetchone()[0], "(0 = не тронута)")
PY
