#!/bin/bash
cat /root/nox/state/c400_imp.rc 2>/dev/null || echo running; ls -la /root/nox/state/c400_imp.json | awk '{print $5}'
python3 -I - <<'PY'
import sqlite3,json
c=sqlite3.connect('file:/root/nox/state/c400_s03_copy.db?mode=ro',uri=True)
print({t:c.execute('select count(*) from %s'%t).fetchone()[0] for t in ('mem_facts','mem_episodes','mem_profile','facts','evidence')})
try:
    d=json.load(open('/root/nox/state/c400_imp.json')); print(d['totals'])
except Exception as e: print('nojson')
PY
