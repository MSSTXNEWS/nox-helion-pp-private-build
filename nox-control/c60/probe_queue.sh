#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-230; }
S=/root/nox/state
echo "== train"; tail -n 3 /root/nox/logs/train_qwen9b_t131u.log | a; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== TASKS_1000"; head -c 900 $S/TASKS_1000_ACTIVATED.json | a; echo; python3 - <<'PY'
import json
try:
    d=json.load(open('/root/nox/state/TASKS_1000_ACTIVATED.json'));print(type(d).__name__, list(d)[:12] if isinstance(d,dict) else len(d))
except Exception as e: print(e)
PY
echo "== activator"; head -c 700 $S/TASKS_1000_ACTIVATOR.json | a; echo; cat $S/TASKS_1000_ACTIVATOR.pid; ps -p $(cat $S/TASKS_1000_ACTIVATOR.pid 2>/dev/null) -o pid,etime,cmd 2>/dev/null | a
echo "== opt queue"; head -c 700 $S/NOX_OPT_QUEUE_T168U.json | a; echo
echo "== agents registry"; python3 -c "
import json;d=json.load(open('/root/nox/state/NOX_PROD_AGENTS_REGISTRY.json'));print(json.dumps(d)[:1500])" | a
echo "== native subagents"; head -c 1200 $S/owner_native_subagents_install_6906985850.json | a; echo
echo "== existing capabilities"; ls /root/nox/scripts | grep -iE "rag|eval|router|reflect|memory|embed" | head -15
ls /root/nox/state | grep -iE "rag|eval|memory|kb_|reflect" | head -10
supervisorctl status | awk '{print $1,$2}' | grep -vE "STOPPED|FATAL" | head -40
