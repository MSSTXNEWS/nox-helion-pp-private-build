echo "C300: rv_g1"
N=/workspace/nox
pkill -f rv_audit.py; pkill -f rv_chat.py; sleep 1
for f in rv_audit.py rv_chat.py; do curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/$f -o /tmp/$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
PY="$N/venv/bin/python -I"; rm -f $N/state/rv/g*.jsonl; uptime
setsid -f bash -c "timeout 900 $PY /tmp/rv_audit.py chat-dc.html writer.html settings.html live.html tv.html voice.html intents.html cinema.html board.html calendar.html photo.html > $N/state/rv/g1.jsonl 2>&1; RV_GL=1 timeout 400 $PY /tmp/rv_audit.py studio.html scene.html > $N/state/rv/g2.jsonl 2>&1; timeout 400 $PY /tmp/rv_chat.py > $N/state/rv/g3.jsonl 2>&1" </dev/null >/dev/null 2>&1
echo started
