echo "C300: srv_k81"
sed -n '64,150p' /workspace/nox/agent/autotrain/autotrain.sh | cut -c1-230
cat /workspace/nox/agent/out/k1_restart.log | tail -3; curl -s -m3 localhost:8104/health | head -c 80; echo
df -h /workspace | tail -1
