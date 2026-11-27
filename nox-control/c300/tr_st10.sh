export RUNNER_TRACKING_ID=""
echo "C300: tr_st10"
N=/workspace/nox; D=$N/ops/dpo
date -u; ps -o pid,stat,etimes,pcpu,args -p 1968385 | cut -c1-100
ls -la $N/state/orch/OWNER_ACTIVE $N/agent/LIVE_TURN 2>&1 | cut -c1-120
tail -c 1500 $D/run7.log | tr '\r' '\n' | tail -8 | cut -c1-220
ps -eo pid,stat,args | grep -E "[k]ill -STOP|char_cycle" | head -3 | cut -c1-100
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader
echo END
