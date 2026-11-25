# O: разведка для арбитра (только чтение)
echo "== ps"; ps -eo pid,ni,stat,pcpu,etimes,cmd --sort=-pcpu | grep -E "autotrain|distill|v5_|ckpt_guard|llama|train" | grep -v grep | cut -c1-220 | head -30
echo "== nvidia-smi"; nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
echo "== api"; for u in /api/chat/health /api/nox/status; do echo "$u $(curl -s -m 4 127.0.0.1:8091$u | head -c 600)"; done
echo "llama $(curl -s -m 4 127.0.0.1:8200/running | head -c 400)"
for u in /svc/agents/ /svc/advisors/; do echo "$u $(curl -s -m 4 -o /dev/null -w '%{http_code}' 127.0.0.1:8091$u) $(curl -s -m 4 127.0.0.1:8091$u | head -c 300)"; done
echo "== files"; ls /workspace/nox/ops | head -40; ls /workspace/nox/state | head -30; cat /workspace/nox/svc/start_extra.sh | tail -15; ls /workspace/nox/agent | head; ls /workspace/nox/ | head -50
echo "== registry"; python3 - <<'P'
import json;r=json.load(open('/workspace/nox/site/qa/registry.json'));print(type(r).__name__, list(r)[:8] if isinstance(r,dict) else len(r))
x=r if isinstance(r,list) else r.get('commands',r.get('items',r))
print(json.dumps(x if not isinstance(x,list) else x[:2],ensure_ascii=False)[:700])
P
ls /workspace/nox/site/qa | head; pgrep -af ckpt_guard | head -3
