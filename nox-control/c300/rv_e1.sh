echo "C300: rv_e1"
N=/workspace/nox
pkill -f rv_audit.py; pkill -f rv_chat.py; sleep 1
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_dg.py -o /tmp/rv_dg.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
uptime; timeout 150 $N/venv/bin/python -I /tmp/rv_dg.py 2>&1 | tail -20 | cut -c1-1500
cut -c1-600 $N/state/rv/d1chat.jsonl
