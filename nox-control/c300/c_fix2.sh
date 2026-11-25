#!/bin/bash
# c_fix2: исправление nox_cmd.py (UnboundLocalError при GET-команде). Бэкап *.bak_c_2, компиляция, рестарт, откат при провале.
set -u
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/cfiles
N=/workspace/nox; S=$N/web/pkg/server
cp -p $S/nox_cmd.py $S/nox_cmd.py.bak_c_2
curl -fsSL $RAW/nox_cmd.py -o $S/nox_cmd.py.new || { echo "download failed"; exit 1; }
python3 -I -m py_compile $S/nox_cmd.py.new || { echo "compile failed"; exit 1; }
mv $S/nox_cmd.py.new $S/nox_cmd.py
$S/run_web.sh restart; sleep 6
H=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/chat/health); echo "health $H"
if [ "$H" != 200 ]; then cp -p $S/nox_cmd.py.bak_c_2 $S/nox_cmd.py; $S/run_web.sh restart; echo ROLLBACK; exit 1; fi
t(){ curl -s -m 25 -w ' [%{http_code}]' -X POST http://127.0.0.1:8091/api/cmd -H 'Content-Type: application/json' -d "$1" | head -c 300; echo; }
echo "T1 unknown: $(t '{"name":"__nope__"}')"
echo "T2 health: $(t '{"name":"health"}')"
echo "T3 svc.status: $(t '{"name":"svc.status"}')"
echo "T4 sleep: $(t '{"name":"sleep"}')"
echo "T5 search no q: $(t '{"name":"search","params":{}}')"
echo "LOG:"; tail -n 4 $N/state/cmd_log.jsonl
echo "DONE"
