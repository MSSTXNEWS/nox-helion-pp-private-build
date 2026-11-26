echo "C300: srv_k111"
D=/workspace/nox/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo
curl -sfL "$R/teacher_dump.py?cb=$(date +%s)" -o $D/teacher_dump.py && python3 -m py_compile $D/teacher_dump.py && echo deployed
pgrep -f "ops/dpo/chain5.sh" >/dev/null && echo "chain5 уже идёт" || { nohup setsid $D/chain5.sh </dev/null >/dev/null 2>&1 & }
sleep 60; tail -n 6 $D/run5.log | cut -c1-200; ls -la /workspace/nox/STOP
