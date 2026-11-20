#!/bin/bash
# Диспетчер: 6 исполнителей (кап 4 -> 6) по явному разрешению владельца. Бэкап и откат при сбое.
D=/root/nox/scripts/nox_dispatcher_t855u.py; C=/etc/supervisor/conf.d/nox-t855u.conf
cp -a $D $D.bak_six; cp -a $C $C.bak_six
sed -i 's/_nrun = max(1, min(_nrun, 4, WORKERS))/_nrun = max(1, min(_nrun, 6, WORKERS))/' $D
if grep -q 'NOX_DISPATCHER_WORKERS="[0-9]*"' $C; then sed -i 's/NOX_DISPATCHER_WORKERS="[0-9]*"/NOX_DISPATCHER_WORKERS="6"/' $C
else sed -i '/nox_dispatcher_t855u.py/,/^environment=/ s/^environment=\(.*\)$/environment=\1,NOX_DISPATCHER_WORKERS="6"/' $C; fi
/root/venv_new/bin/python -m py_compile $D || { cp -a $D.bak_six $D; echo "SYNTAX FAIL rollback"; exit 0; }
P=$(grep -B2 'nox_dispatcher_t855u.py' $C | grep -oE '^\[program:[^]]+' | cut -d: -f2 | head -1); P=${P:-nox-dispatcher-t855u}
supervisorctl reread >/dev/null; supervisorctl update >/dev/null; supervisorctl restart $P 2>&1 | tail -1
sleep 25
supervisorctl status $P | cut -c1-90
grep -E "steal threads|WORKERS" /root/nox/logs/dispatcher_t855u.log | tail -2 | cut -c1-160
if ! supervisorctl status $P | grep -q RUNNING; then cp -a $D.bak_six $D; cp -a $C.bak_six $C; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; supervisorctl restart $P >/dev/null; echo ROLLBACK; fi
