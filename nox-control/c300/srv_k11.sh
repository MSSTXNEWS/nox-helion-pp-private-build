echo "C300: srv_k11"
cat /etc/supervisor/conf.d/nox_tools_gateway.conf
echo "== callers"; grep -rIl "tools_gateway\|8143" /workspace/nox --include=*.py --include=*.sh --include=*.json --include=*.conf --include=*.yaml 2>/dev/null | grep -v "/venv/\|node_modules\|\.bak" | head -15
echo "== 8143 refs"; grep -rIn "8143" /workspace/nox --include=*.py --include=*.sh --include=*.json --include=*.conf 2>/dev/null | grep -v "/venv/\|node_modules\|\.bak" | cut -c1-220 | head -10
echo "== tools"; which supergateway mcp-proxy npx node 2>&1 | head
echo "== r033/train"; ls -t /workspace/nox/distill_v2 | head -8; ls /workspace/nox/state/p3/eval 2>/dev/null | head
ls -t /workspace/nox/agent/autotrain/*.log 2>/dev/null | head -3
