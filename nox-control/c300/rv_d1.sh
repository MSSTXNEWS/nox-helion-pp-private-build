echo "C300: rv_d1"
N=/workspace/nox
pkill -f rv_audit.py; pkill -f rv_chat.py
for f in rv_audit.py rv_chat.py; do curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/$f -o /tmp/$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
PY="$N/venv/bin/python -I"
rm -f $N/state/rv/d1*.jsonl
setsid -f bash -c "$PY /tmp/rv_chat.py > $N/state/rv/d1chat.jsonl 2>&1; $PY /tmp/rv_audit.py chat-dc.html writer.html > $N/state/rv/d1a.jsonl 2>&1" </dev/null >/dev/null 2>&1
echo started
