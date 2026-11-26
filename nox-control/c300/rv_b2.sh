echo "C300: rv_b2"
N=/workspace/nox; W=$N/web/site
mkdir -p $N/state/rv; for f in rv_audit.py rv_chat.py; do curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/$f -o /tmp/$f; done
ls $W/*.html | xargs -n1 basename | tr '\n' ' '; echo
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
PY="$N/venv/bin/python -I"
A="writer.html $(cd $W; ls studio*.html writer*.html 2>/dev/null | grep -v '^writer.html$' | tr '\n' ' ') system.html memory.html settings.html training.html photo.html calendar.html"
B="constructor.html tools.html pdf.html cinema.html tv.html assistant.html board.html intents.html chat.html consciousness.html selffeel.html soul.html organism.html growth.html models.html music.html voice.html scene.html effects.html widgets.html news.html about.html integrations.html glance.html dispatcher.html downloads.html projects.html install.html"
echo $A > $N/state/rv/listA; echo $B > $N/state/rv/listB
setsid -f bash -c "$PY /tmp/rv_chat.py > $N/state/rv/chat.jsonl 2> $N/state/rv/chat.err; $PY /tmp/rv_audit.py $A > $N/state/rv/a.jsonl 2> $N/state/rv/a.err" </dev/null >/dev/null 2>&1
setsid -f bash -c "$PY /tmp/rv_audit.py $B > $N/state/rv/b.jsonl 2> $N/state/rv/b.err" </dev/null >/dev/null 2>&1
echo started
