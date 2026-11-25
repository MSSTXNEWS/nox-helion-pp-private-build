echo "C300: d_p1"
cat /workspace/nox/svc/d_install.log; tail -3 /workspace/nox/svc/d_install.out | cut -c1-200; df -BG /workspace|tail -1; pgrep -f d_svc_install >/dev/null && echo RUNNING || echo FINISHED
