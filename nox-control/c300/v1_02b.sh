echo "K1: v1_02b"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
echo "--- 8104 args"
tr '\0' ' ' < /proc/$(pgrep -f "port 8104" | head -1)/cmdline | cut -c1-900; echo
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>&1 | head -3
echo "--- chat_core 322-470"
sed -n 322,470p $W/web/pkg/server/chat_core.py | cut -c1-210
echo END
