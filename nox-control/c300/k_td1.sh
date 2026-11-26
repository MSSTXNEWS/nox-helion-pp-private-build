echo "C300: k_td1"
D=/workspace/nox/memory
ls -la --time-style=+%H:%M $D | grep -E "test|synth" 
find $D/test_disk -maxdepth 2 -printf "%y %s %TH:%TM %p\n" 2>/dev/null | head -15
du -sh $D/test_disk 2>/dev/null
lsof +D $D/test_disk 2>/dev/null | head -5
grep -rlE "test_disk|tmp_disk_test|synth_test" /workspace/nox/stewards /workspace/nox/agents /workspace/nox/ops /workspace/nox/brain /workspace/nox/agent/out /workspace/nox/canon /tmp 2>/dev/null | head -10
df -h /workspace | tail -1
