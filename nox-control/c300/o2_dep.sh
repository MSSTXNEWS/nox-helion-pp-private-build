echo "K1: o2_dep"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=$N/mods; T=$N/state/tasks
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/organism; cb=$(date +%s)
W=$(mktemp -d); F="nox_org_common nox_ledger nox_organism nox_sleep nox_absorb nox_predator nox_bus nox_dispatch nox_board nox_hands test_nox_organism test_nox_predator test_nox_hands"
for f in $F; do curl -fsS -m 30 "$B/$f.py?cb=$cb" -o $W/$f.py || { echo "FETCH_FAIL $f"; echo END; exit 0; }; python3 -m py_compile $W/$f.py || { echo "COMPILE_FAIL $f"; echo END; exit 0; }; done
cp $M/autonomy.py $W/autonomy.py
R=$(cd $W && python3 -W ignore -m unittest test_nox_hands test_nox_predator test_nox_organism 2>&1 | tail -45); echo "$R" | cut -c1-200; echo "$R" | grep -q "^OK$" || { echo "TESTS_FAIL abort"; echo END; exit 0; }
echo "before: tasks_queued=$(grep -l '"status": "queued"' $T/*.json 2>/dev/null | wc -l) receipts=$(ls $N/state/receipts | wc -l) bus_events=$(python3 -c "import sqlite3;print(sqlite3.connect('file:$N/state/bus/events.db?mode=ro',uri=True).execute('select max(seq) from events').fetchone()[0])") disk=$(df -BM /workspace|tail -1|awk '{print $4}')"
echo "chat_busy src:"; grep -n -A8 "def chat_busy" $N/agent/nox_ops/common.py | cut -c1-160
for f in nox_bus nox_dispatch nox_board nox_hands test_nox_hands; do cp $M/$f.py $M/$f.py.bak_o2 2>/dev/null; cp $W/$f.py $M/$f.py; done
D=/etc/supervisor/conf.d
[ -f $D/nox_hands.conf ] || cat > $D/nox_hands.conf <<'CONF'
[program:nox_hands]
command=nice -n 10 python3 -I /workspace/nox/mods/nox_hands.py --daemon
directory=/workspace/nox/mods
autostart=true
autorestart=true
startretries=5
startsecs=3
stopsignal=TERM
stopwaitsecs=10
redirect_stderr=true
stdout_logfile=/workspace/nox/logs/nox_hands.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=3
environment=NOX_ROOT="/workspace/nox"
CONF
supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -1; supervisorctl restart nox_hands 2>&1 | tail -1; sleep 60; supervisorctl status nox_hands
echo "after: $(python3 -I - <<'PY'
import json,glob,collections,sqlite3
N="/workspace/nox"; c=collections.Counter(json.load(open(p,encoding="utf-8")).get("status") for p in glob.glob(N+"/state/tasks/*.json")); print("tasks",dict(c))
cn=sqlite3.connect("file:"+N+"/state/bus/events.db?mode=ro",uri=True); print("task events",cn.execute("select kind,count(*) from events where seq>(select max(seq)-5000 from events) and kind like 'task.%' group by kind").fetchall(), "max_seq",cn.execute("select max(seq) from events").fetchone()[0])
PY
)"
echo "receipts_done=$(grep -l '"done": true' $N/state/receipts/*.json 2>/dev/null | wc -l) artifacts=$(ls $T/artifacts 2>/dev/null | wc -l) disk=$(df -BM /workspace|tail -1|awk '{print $4}')"
python3 -I - <<'PY'
import sys,time,json,glob; sys.path.insert(0,"/workspace/nox/mods")
import nox_board as BD, nox_hands as H, nox_org_common as C
b=C.load_json("/workspace/nox/state/core/board.json"); print("board slots",len(b["slots"]),list(b["slots"]),"age_s",round(time.time()-b["t"],1))
for q in ("как там обучение?","как там задача про список дел?","как тело?","какая цель?"):
    a=BD.answer(q); print("ASK",q,"ms",a["ms"],"slots",a["slots"],"len",len(a["text"]))
ids=[json.load(open(p))["id"] for p in glob.glob("/workspace/nox/state/tasks/task-*.json")][:3]
print("can_claim_done",[H.can_claim_done(i) for i in ids])
PY
tail -3 $N/logs/nox_hands.log | cut -c1-200
rm -rf $W; echo END
