echo "C300: srv_k1"
echo "== svc"; for p in 8091 8104 8141 8142 8143 8300 8793 8810 18217; do printf "%s " $p; curl -s -o /dev/null -m 5 -w "%{http_code}\n" http://127.0.0.1:$p/ ; done
echo "== supervisor"; supervisorctl status 2>&1 | head
echo "== vram"; nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
echo "== disk"; df -h /workspace | tail -1
echo "== theme"; stat -c %s /workspace/nox/web/site/nox-theme.js
echo "== train"; ps aux | grep -E "autotrain|distill_v2|axis_guard" | grep -v grep | awk '{print $11,$12,$13}' | head
cat /workspace/nox/state/p3/train_verdict.json 2>&1 | head -c 600; echo
ls -t /workspace/nox/state/p3 | head -8
echo "== worms"; ls /workspace/nox/nox-control/c300 2>/dev/null | head -0; grep -rln "worm" /workspace/nox --include=*.py 2>/dev/null | head -8
curl -s -m 15 http://127.0.0.1:8810/worms/night | head -c 800; echo
tail -5 /workspace/nox/state/p3/r033*.log 2>/dev/null
