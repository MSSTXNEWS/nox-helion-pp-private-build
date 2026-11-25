echo "C300: a2_ops1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/cff938156a288686500f9db90e1c347e3b9edbc2/nox-control/c300; A=/workspace/nox/agents
echo "== needs_owner"; python3 - <<'P'
import sqlite3,json
c=sqlite3.connect('/workspace/nox/agents/book.sqlite'); c.row_factory=sqlite3.Row
for r in c.execute("select id,title,project,team,substr(goal,1,70) g,returns,restarts from tasks where status in ('needs_owner','failed')"):
    last=c.execute("select kind,substr(text,1,110) t from steps where task=? and kind in ('review','error','escalate','stopper') order by id desc limit 1",(r['id'],)).fetchone()
    print(dict(r), '|', tuple(last) if last else None)
P
echo "== chat uses /llm?"; grep -rIl "svc/agents/llm\|8810/llm" /workspace/nox/web /workspace/nox/site 2>/dev/null | grep -v vendor | head; grep -rIl "8810\|svc/agents" /workspace/nox/web/*.py /workspace/nox/web/pkg 2>/dev/null | head -5
echo "== chat path"; grep -rn "api/chat" /workspace/nox/web/*.py 2>/dev/null | head -3 | cut -c1-160
