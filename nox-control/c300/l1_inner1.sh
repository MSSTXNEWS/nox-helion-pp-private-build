echo "K1: l1_inner1"
cd /workspace/nox/agent/nox_agents
grep -rn "мыслей не отвечает" --include=*.py . | cut -c1-200 | head -5
grep -n "NOX_SEED_URL\|NOX_FAST_URL\|def make_chat_busy\|DONOR_URL\|def think\|def ask\|timeout" inner_loop.py | cut -c1-190 | head -30
grep -n "def .*donor\|DONOR_URL\|def chat_llm\|def llm" lib.py | cut -c1-180 | head -15
echo "inner_in_cron: $(grep -c inner /workspace/nox/agent/nox_agents/run_supervisor.sh)"; pgrep -af inner_loop | wc -l
echo "slots8105: $(curl -s -m3 localhost:8105/slots | python3 -c 'import json,sys;print([int(x["is_processing"]) for x in json.load(sys.stdin)])')"
