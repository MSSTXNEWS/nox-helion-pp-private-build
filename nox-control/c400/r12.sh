#!/bin/bash
echo "IMP rc: $(cat /root/nox/state/c400_imp.rc 2>/dev/null || echo running)"
echo GENOME: $(find /root /opt /home -maxdepth 8 \( -iname 'genome_engine.py' -o -iname 'core_adapter.py' -o -ipath '*/GENOME' \) 2>/dev/null | head -3 | tr '\n' ' ')
echo "ENVFILES: $(grep -lE '(GROQ|CEREBRAS|OPENROUTER|GEMINI|MISTRAL|NVIDIA)_API_KEY' /root/nox/config/* /root/nox/*.env /root/nox/.env /root/.nox_env /etc/nox* 2>/dev/null | tr '\n' ' ')"
for f in /root/nox/config/*.env /root/nox/.env /root/.nox_env; do [ -f $f ] && set -a && . $f 2>/dev/null; done; set +a
echo "KEYS set: $(for k in GROQ CEREBRAS OPENROUTER GEMINI MISTRAL NVIDIA; do v=${k}_API_KEY; [ -n "${!v}" ] && echo -n "$k "; done)"
cd /root/nox/repo/nox-control/wow7/adv && timeout 200 python3 health_check.py --timeout 25 --receipt /root/nox/receipts/C400-ADV-HEALTH.json 2>&1 | cut -c1-170 | tail -22
echo BRAT: $(grep -rlE "(^|[^а-я])брат(ан|а|у|е)?([^а-я]|$)" /root/nox/repo/nox-control/glm53 /root/nox/repo/nox-control/qs6 /root/nox/repo/nox-control/wow7/prime /root/nox/config 2>/dev/null | grep -v test_ | head -5 | tr '\n' ' ')
python3 -I - <<'PY'
import sqlite3
c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
for t,col in (('mem_profile','*'),('mem_facts','*')):
    try:
        cols=[r[1] for r in c.execute('pragma table_info(%s)'%t)]
        tc=[x for x in cols if x in('text','value','body','content')][:1]
        if tc: print(t,'брат-обращений:',c.execute("select count(*) from %s where lower(%s) like '%%брат,%%' or lower(%s) like 'брат %%' or lower(%s) like '%%, брат%%'"%(t,tc[0],tc[0],tc[0])).fetchone()[0],cols[:6])
    except Exception as e: print(t,e)
PY
