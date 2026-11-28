N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/bundles/pub"; TS=$(date +%s); BK=$N/state/s4_backups; mkdir -p $BK
echo "S4P1X $(date +%F_%H:%M)"
W=$N/mods/weekly_exam.py; T=$(mktemp -d); curl -fsSL "$RAW/weekly_exam.py?cb=$TS" -o $T/weekly_exam.py && python3 -I -m py_compile $T/weekly_exam.py && grep -q chat_uptime_24h $T/weekly_exam.py || { echo "FAIL fetch"; exit 0; }
cp -a $W $BK/weekly_exam.py.$TS; cp $T/weekly_exam.py $W; supervisorctl restart nox_weekly_exam 2>&1 | tail -1
python3 -I - <<'PY'
import sys; sys.path.insert(0,"/workspace/nox/mods")
import weekly_exam as W
v,f,why=W.p1(); print({k:v.get(k) for k in ("chat_uptime_24h","chat_uptime_samples","uptime_h")}, f)
PY
echo "## uptime now"; tail -n 2 $N/state/uptime.log | cut -c1-200; cat $N/state/core/uptime_daily.json | head -c 300; echo; tail -n 3 $N/state/alerts.jsonl | cut -c1-160
