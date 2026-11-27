export RUNNER_TRACKING_ID=""
echo "C300: tr_st8"
N=/workspace/nox; D=$N/ops/dpo
date -u; uptime | sed 's/.*load/load/'; df -h /workspace | tail -1 | cut -c1-60
ps -eo pid,etimes,args | grep -E "[b]uild_dpo4|[t]rain_dpo|[r]el_gates" | cut -c1-90
tail -3 $D/build4.log | cut -c1-200; wc -l $D/dpo4_jm.jsonl 2>&1 | tail -1
tail -4 $D/run7.log | cut -c1-250; tail -3 $N/agent/out/char_cycle.log | cut -c1-200
echo END
