echo "C300: ui_scr2"; L=/workspace/nox/agent/out/ui_sc.log; tail -8 $L | cut -c1-200; ls /workspace/nox/agent/out/ui_sc | wc -l
echo "LHDONE $(grep -c "ALL LH DONE" $L)"; ls /workspace/nox/agent/out/ui_sc | grep -c lh; /workspace/nox/venv/bin/python /workspace/nox/tools/uiscore/report.py 2>&1 | head -45
