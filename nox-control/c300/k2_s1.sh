echo "C300: k2_s1"
N=/workspace/nox; ST=$N/state; O=$N/agent/out
echo "restart:"; tail -3 $ST/k2_restart.log | cut -c1-160
echo "job2:"; cat $ST/k2_job2.log 2>&1 | cut -c1-260
echo "r8105:"; cat $ST/k2_r8105.log | cut -c1-200
echo "bind errs: 8301=$(grep -c 'already in use' $O/adapter_mem_8301.log) 8090=$(grep -c 'already in use' $O/core_8090.log)"
echo "meili ERR total=$(grep -c ERROR $N/svc/logs/meili.log) last: $(grep ERROR $N/svc/logs/meili.log | tail -1 | cut -c1-30)"; tail -2 $N/svc/logs/index.log 2>/dev/null
echo "gb10 tun: $(pgrep -f gb10_judge_tunnel | wc -l) ; webchat tun: $(supervisorctl status nox_web_chat_tunnel | cut -c1-60)"
echo "invoke: $(pgrep -f invokeai-web | wc -l) ; t_coder 8143: $(ss -ltn | grep -c ':8143 ')"
free -g | sed -n 2p; nvidia-smi --query-gpu=memory.used --format=csv,noheader; uptime
