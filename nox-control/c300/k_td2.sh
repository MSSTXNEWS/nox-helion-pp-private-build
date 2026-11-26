echo "C300: k_td2"
df -h /workspace | tail -1
F=/workspace/nox/memory/test_disk/bigfile
lsof "$F" 2>/dev/null | head -3
[ -f "$F" ] && rm -f "$F" && echo "removed test bigfile"
rmdir /workspace/nox/memory/test_disk /workspace/nox/memory/tmp_disk_test /workspace/nox/memory/synth_test 2>/dev/null
df -h /workspace | tail -1
grep -n "test_disk\|bigfile" /workspace/nox/brain/BRAIN/test_core_view.py /workspace/nox/brain/DSP/test_dsp.py 2>/dev/null | head -5
