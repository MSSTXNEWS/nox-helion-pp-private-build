echo "C300: rv_g3"
N=/workspace/nox
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_audit.py -o /tmp/rv_audit2.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
PY="$N/venv/bin/python -I"; uptime; pgrep -af "rv_audit|rv_chat" | cut -c1-70
for f in g2 g3; do echo "== $f"; cut -c1-700 $N/state/rv/$f.jsonl | grep -v -E "^ |Traceback|File|Exception|handle" | head -14; done
setsid -f bash -c "timeout 800 $PY /tmp/rv_audit2.py settings.html live.html tv.html voice.html intents.html cinema.html board.html calendar.html photo.html > $N/state/rv/g4.jsonl 2>&1" </dev/null >/dev/null 2>&1
echo started
