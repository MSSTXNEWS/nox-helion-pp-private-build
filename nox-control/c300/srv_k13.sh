echo "C300: srv_k13"
curl -s -m 5 -o /dev/null -w "8130 before %{http_code}\n" http://127.0.0.1:8130/health
cat /workspace/nox/tools/run_tools_gateway.sh | head -12
OLD=$(ss -ltnp | grep ":8130 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo old=$OLD
kill $OLD; sleep 3
supervisorctl start nox_tools_gateway 2>&1 | tail -1; sleep 8
supervisorctl status nox_tools_gateway
curl -s -m 5 -o /dev/null -w "8130 after %{http_code}\n" http://127.0.0.1:8130/health
echo "== train"
cd /workspace/nox
ls -t distill_v2 | head -3; ls distill_v2/ckpt 2>/dev/null | tail -3
ls -t agent/autotrain | head -8
tail -5 $(ls -t agent/autotrain/*.log 2>/dev/null | head -1) | cut -c1-250
grep -n "moe_backend\|unsloth_triton\|liger\|torch.compile\|r033" distill_v2.py agent/autotrain/autotrain.sh | cut -c1-200 | head -20
ls state/p3 | head -30
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
