echo "C300: tr_chk3"
D=/workspace/nox/ops/dpo
date -u; ps -eo pid,etimes,args | grep -E "rel_gates|watch1|build_dpo3" | grep -v grep | cut -c1-90
grep -a -E "^[0-9:]{8} " $D/relgates_run1.log | tail -4 | cut -c1-400
tail -4 $D/watch1.log | cut -c1-500; ls /workspace/nox/state/p3/dpo_pending 2>&1 | tail -1
df -h /workspace | tail -1 | cut -c1-60; uptime
echo END
