#!/bin/bash
C=/root/.kit6_ctr; n=$(cat $C 2>/dev/null || echo 0); echo $((n+1)) > $C; echo "CHUNK $n"
S=/root/nox/soul_kit
if [ $n = 0 ]; then
 cd /root/nox; wc -l web_server.py nox_life.py | tr '\n' ' '; echo
 grep -n -i -E "persona|system_prompt|SYSTEM_PROMPT|soul|passport|NOX_ID|def build_sys|8095|recall" web_server.py | cut -c1-150 | head -25
 echo ---; grep -n -i -E "persona|system|passport|soul" nox_life.py | cut -c1-120 | head -10
 echo ---; python3 - <<'PY'
import sqlite3
c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
for n,s in c.execute("select name,sql from sqlite_master where type='table'"): print(n,c.execute(f'select count(*) from "{n}"').fetchone()[0], s[:90].replace('\n',' '))
PY
else tr -s ' \n' < $S/12_Living_NOX/01_BEGIN_LIVING_NOX.md | tail -c +$(((n-1)*2900+1)) | head -c 2900; fi
