echo "C300: d_p1"
tail -8 /workspace/nox/svc/d_install.log; tail -15 /workspace/nox/svc/d_fix3.out | cut -c1-200 | cut -c1-300; df -BG /workspace|tail -1; pgrep -f d_svc_install >/dev/null && echo RUNNING || echo FINISHED
grep -m3 -E "Caused by|Error|Exception" /workspace/nox/svc/logs/stirling.log | cut -c1-300
du -sh /workspace/nox/svc/* 2>/dev/null | sort -h | tail -6
