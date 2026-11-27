export RUNNER_TRACKING_ID=""
echo "C300: tr_st9"
N=/workspace/nox; D=$N/ops/dpo
date -u; uptime | sed 's/.*load/load/'; df -h /workspace | tail -1 | cut -c1-60; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
ps -eo pid,etimes,args | grep -E "[b]uild_dpo4|[t]rain_dpo|[r]el_gates|[a]utotrain" | cut -c1-90
tail -2 $D/build4.log | cut -c1-200; wc -l $D/dpo4_jm.jsonl 2>&1 | tail -1
tail -5 $N/agent/out/char_cycle.log | cut -c1-200
grep -a -E "^[0-9:]{8} (A/B|ОТНОС|ext)" $D/run7.log | tail -4 | cut -c1-500
tail -c 600 $D/run7.log | cut -c1-300
ls -t $N/distill_v2/gates/decision_*.json | head -2; cat $N/agent/out/ckpt_best_global.json | head -c 250
echo END
