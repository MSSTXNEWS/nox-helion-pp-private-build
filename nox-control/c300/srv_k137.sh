echo "C300: srv_k137"
cd /workspace/nox
ls -la --time-style=+%T state/accel_tok_budget* 2>&1; cat state/accel_tok_budget 2>/dev/null
grep -rh "tok_budget\|ACCEL_TOKB" distill_v2/*.log agent/autotrain/rounds/r039/* 2>/dev/null | tail -5 | cut -c1-200
ls agent/autotrain/rounds/r039/; tail -n 5 agent/autotrain/rounds/r039/*.log 2>/dev/null | cut -c1-200
ls state/core/disk_low.flag 2>&1; nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader
