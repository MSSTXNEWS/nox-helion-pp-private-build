export RUNNER_TRACKING_ID=""
echo "C300: tr_st7"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
date -u; uptime | sed 's/.*load/load/'; df -h /workspace | tail -1 | cut -c1-70
ps -eo pid,etimes,args | grep -E "[r]el_gates|[w]atch2|[b]uild_dpo3|[t]rain_dpo" | cut -c1-90
grep -a -E "^[0-9:]{8} (A/B|ОТНОС|ext)" $D/relgates_run3.log | tail -4 | cut -c1-600
cat $D/watch2.log 2>&1 | cut -c1-600
tail -3 $D/build3.log | cut -c1-500; ls $N/state/p3/dpo_pending 2>&1; wc -l $D/dpo3_train.jsonl 2>&1
grep -c TR_LIMITS $D/char_cycle.sh; tail -3 $N/agent/out/char_cycle.log | cut -c1-200
echo END
