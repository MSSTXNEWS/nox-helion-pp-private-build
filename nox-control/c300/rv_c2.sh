echo "C300: rv_c2"
N=/workspace/nox
pkill -f rv_audit.py; sleep 1
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_audit.py -o /tmp/rv_audit.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
PY="$N/venv/bin/python -I"
ALL="index.html $(cat $N/state/rv/listA) $(cat $N/state/rv/listB)"
set -- $ALL; H=$(( ($# + 1) / 2 )); P1="${@:1:$H}"; P2="${@:$((H+1))}"
setsid -f bash -c "$PY /tmp/rv_audit.py --w1440 $P1 > $N/state/rv/p1.jsonl 2> $N/state/rv/p1.err" </dev/null >/dev/null 2>&1
setsid -f bash -c "$PY /tmp/rv_audit.py --w1440 $P2 > $N/state/rv/p2.jsonl 2> $N/state/rv/p2.err" </dev/null >/dev/null 2>&1
echo started $#; cut -c1-1800 $N/state/rv/chat2.jsonl
