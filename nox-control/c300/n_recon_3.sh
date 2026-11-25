echo "C300: n_recon_3"
cd /workspace/nox/web/pkg/server
sed -n 283,297p chat_core.py | cut -c1-240
echo "== liska_feedback"; sed -n 1,60p liska_feedback.py | cut -c1-200
echo "== morning"; grep -n "_v7_morning" -A25 web_server.py | head -50 | cut -c1-200
echo "== outbox sample"; tail -n 2 /workspace/nox/state/core/outbox_owner.jsonl 2>&1 | cut -c1-400
echo "== nox_cmd head"; sed -n 1,40p nox_cmd.py | cut -c1-200; grep -n "def \|/задач\|/help" nox_cmd.py | head -30
echo "== chat api"; grep -n '"/api/chat' web_server.py | head; grep -n "MODES\|^LENGTH\|^RTE\|^HIST_MAX" chat_core.py | head
ls /workspace/nox/web/site/qa/rework | grep -c fixed; cat /workspace/nox/web/site/qa/rework/chat.fixed 2>&1 | tail -3 | cut -c1-200
cat /workspace/nox/state/persona.json | python3 -c "import json,sys;d=json.load(sys.stdin);d['system_hint']=d['system_hint'][:50];print(d)"
