#!/bin/bash
# c400/r6: бэкап s03.db (только чтение живой БД) + пробный импорт на КОПИИ
df -h /root | tail -1 | awk '{print "free",$4}'
TS=$(date +%Y%m%d_%H%M%S); B=/root/nox/memory/backups/s03_pre_c400_$TS.sqlite
python3 -I - "$B" <<'PY'
import sqlite3,sys
src=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True); dst=sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close()
c=sqlite3.connect(sys.argv[1]); print('backup',sys.argv[1],c.execute('pragma integrity_check').fetchone(),c.execute('select count(*) from mem_facts').fetchone())
PY
cp "$B" /root/nox/state/c400_s03_copy.db
cd /root/nox/repo/nox-control && python3 -m qs6.import_cli --db /root/nox/state/c400_s03_copy.db --root /root/nox/backup_s2/unpacked --dry-run --json > /root/nox/state/c400_dry.json 2>&1; echo rc=$?
python3 -I - <<'PY'
import json
d=json.load(open('/root/nox/state/c400_dry.json'))
print(d['totals'],d['rejected_reasons'])
for f in d['files']:
    if f['facts'] or f['episodes'] or f['profile'] or f['updated'] or f['rejected']: print(f['path'][-60:],f['format'],f['facts'],f['episodes'],f['profile'],f['updated'],sum(f['rejected'].values()))
print(len(d['skipped_files']),'skipped')
PY
