echo "C300: k2_s7"
N=/workspace/nox; O=$N/agent/out
cat $N/state/k2_t3.log
echo "bind errs: 8301=$(grep -c 'already in use' $O/adapter_mem_8301.log) 8090=$(grep -c 'already in use' $O/core_8090.log)"
echo "meili ERR total=$(grep -c ERROR $N/svc/logs/meili.log)"
echo "8143=$(ss -ltn | grep -c ':8143 ') invoke=$(pgrep -f invokeai-web | wc -l) gb10tun=$(pgrep -f gb10_judge_tunnel | wc -l)"
free -g | sed -n 2p; df -BG /workspace | tail -1; nvidia-smi --query-gpu=memory.used --format=csv,noheader; uptime
