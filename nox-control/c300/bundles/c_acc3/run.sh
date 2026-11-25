set -x
N=/workspace/nox; W=$N/web/pkg/server; S=$N/web/site; P=$N/svc/pipeline; B=$P/acc3; O=$N/state/c_acc3.out; : > $O
exec >> $O 2>&1
echo "== install kanban+css"; cp $B/nox-chat-kanban.js $S/; cp $B/nox-chat-c.css $S/
grep -q nox-chat-kanban.js $S/chat.html || sed -i 's#</body>#<script src="./nox-chat-kanban.js?v=c1" defer></script>\n</body>#' $S/chat.html
sed -i 's#nox-chat-c.css?v=c1#nox-chat-c.css?v=c3#' $S/chat.html; grep -c "nox-chat-kanban\|nox-chat-c.css" $S/chat.html
echo "== registry nox-a2"; R=$W/svc_registry.json; [ -f $R.bak_c_1 ] || cp $R $R.bak_c_1
python3 - <<'PY'
import json
p="/workspace/nox/web/pkg/server/svc_registry.json"; r=json.load(open(p))
r["nox-a2"]={"port":8810,"mode":"strip","title":"NOX A2 доска задач","ui":False,"note":"GET /board, /task/{id}/card (чтение для виджета канбан в чате)"}
json.dump(r,open(p,"w"),ensure_ascii=False,indent=1); print("registered",len(r))
PY
( $W/run_web.sh restart </dev/null >/tmp/c_web_restart.log 2>&1 ); sleep 7
curl -s -m6 localhost:8091/svc/nox-a2/board | head -c 200; echo
echo "== live ui (real chat, slow)"
for PY in $N/venv/bin/python python3 $N/venv_tools/bin/python; do $PY -c "import playwright" 2>/dev/null && { echo using $PY; timeout 420 $PY $B/live_ui.py; break; }; done
echo "== pipe_err"; tail -8 $N/state/pipe_err.log
echo "== qa_audit chat (bg-limited)"; cp $S/qa/audit.json $S/qa/audit.json.bak_c_1 2>/dev/null
cd $N && for PY in $N/venv/bin/python python3; do $PY -c "import playwright" 2>/dev/null && { timeout 900 $PY $N/qa_audit.py chat.html | tail -30; break; }; done
python3 -c "
import json;d=json.load(open('$S/qa/audit.json'));c=d.get('chat');print(json.dumps(c,ensure_ascii=False)[:1800])"
echo FINISHED
