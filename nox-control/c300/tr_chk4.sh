echo "C300: tr_chk4"
D=/workspace/nox/ops/dpo
date -u; tail -c 1500 $D/relgates_run1.log | cut -c1-300; ls -la $D/watch1.sh $D/watch1.log 2>&1 | cut -c1-120
dmesg 2>/dev/null | grep -i -E "killed process|out of memory" | tail -3; cat /workspace/nox/state/p3/killed.txt 2>/dev/null | tail -3 | cut -c1-200
free -g | sed -n 2p
echo END
