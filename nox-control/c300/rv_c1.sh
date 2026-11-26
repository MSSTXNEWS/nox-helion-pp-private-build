echo "C300: rv_c1"
N=/workspace/nox
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_chat.py -o /tmp/rv_chat.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
setsid -f bash -c "$N/venv/bin/python -I /tmp/rv_chat.py > $N/state/rv/chat2.jsonl 2> $N/state/rv/chat2.err" </dev/null >/dev/null 2>&1
pgrep -af rv_audit | cut -c1-80; uptime
