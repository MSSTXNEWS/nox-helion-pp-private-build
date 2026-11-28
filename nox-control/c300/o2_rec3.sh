echo "K1: o2_rec3"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== ops_core"; sed -n 1,90p $N/agent/nox_ops/ops_core.py | cut -c1-170
echo "== svc_dispatcher"; wc -l $N/agent/nox_ops/svc_dispatcher.py; grep -nE "^def |^class |tasks|queued|status|STATE|INTERVAL" $N/agent/nox_ops/svc_dispatcher.py | head -40 | cut -c1-190
echo "== chat_core tasks"; grep -nE "state/tasks|\"queued\"|'queued'|_RECEIPT|def _task|def .*receipt|TASKS" $N/web/pkg/server/chat_core.py | head -25 | cut -c1-200
echo "== board keys"; python3 -I - <<'PY'
import sqlite3
cn=sqlite3.connect("file:/workspace/nox/state/bus/events.db?mode=ro",uri=True,timeout=3)
for k,v,ts in cn.execute("select k,substr(v,1,70),ts from board"): 
    import re; print(k,"|",re.sub(r"[А-Яа-я]+","w",v))
PY
echo END
