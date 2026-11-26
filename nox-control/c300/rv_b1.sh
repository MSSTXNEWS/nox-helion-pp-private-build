echo "C300: rv_b1"
N=/workspace/nox
mkdir -p $N/state/rv; curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_audit.py -o /tmp/rv_audit.py
rm -f $N/state/rv/b1.jsonl
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
setsid -f bash -c "$N/venv/bin/python -I /tmp/rv_audit.py index.html chat-dc.html > $N/state/rv/b1.jsonl 2> $N/state/rv/b1.err" </dev/null >/dev/null 2>&1
echo started
