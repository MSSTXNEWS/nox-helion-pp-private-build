echo "K1: q28_state"
export RUNNER_TRACKING_ID=""
echo "train_dpo procs=$(pgrep -fc train_dpo) char_cycle=$(pgrep -fc char_cycle) 8104=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8104/health) 8142=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8142/health) 8141=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8141/health)"
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits | head -1
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | awk -F, '{print $2}' | tr '\n' ' '; echo
for p in 8104 8142 8141 8152; do pid=$(ss -ltnp | grep "127.0.0.1:$p " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo "$p up_s=$(ps -o etimes= -p $pid 2>/dev/null) ngl=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oE -- '(-ngl|--n-gpu-layers) [0-9a-z]+' | head -1) ctx=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oE -- '(-c|--ctx-size) [0-9]+' | head -1) parallel=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oE -- '(-np|--parallel) [0-9]+' | head -1)"; done
ls /workspace/nox/state/orch 2>/dev/null | head -8 | tr '\n' ' '; echo "owner_active_age=$(( $(date +%s) - $(stat -c %Y /workspace/nox/state/orch/OWNER_ACTIVE 2>/dev/null || echo 0) ))s"
tail -3 /workspace/nox/ops/dpo/char_cycle.log 2>/dev/null | cut -c1-120 | sed -E 's/[0-9a-f]{20,}//g'
echo END
