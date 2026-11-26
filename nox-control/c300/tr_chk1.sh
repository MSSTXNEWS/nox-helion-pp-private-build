echo "C300: tr_chk1"
N=/workspace/nox; D=$N/ops/dpo
date -u; ps -eo pid,etimes,args | grep -E "rel_gates|build_dpo3|guard_eval|p3_axis_guard" | grep -v grep | cut -c1-120
tail -3 $D/build3.log | cut -c1-300; tail -2 $D/relgates_run1.log | cut -c1-300
tail -3 $N/state/p3/axis_guard.err 2>/dev/null
echo END
