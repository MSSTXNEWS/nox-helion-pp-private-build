echo "C300: srv_k66"
: > /workspace/nox/ops/dpo/run2.log
nohup setsid /workspace/nox/ops/dpo/chain4.sh </dev/null >/dev/null 2>&1 &
sleep 2; pgrep -f chain4.sh | head -1; ls /workspace/nox/STOP
