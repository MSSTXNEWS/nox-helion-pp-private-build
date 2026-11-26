echo "C300: k2_r3"
N=/workspace/nox
S(){ sed -E 's/(key|token|secret|password)([=: ]+)[A-Za-z0-9_\-]{8,}/\1\2***/Ig;s/--master-key [^ ]+/--master-key ***/g'; }
echo "--- owner_active"; cat $N/state/orch/OWNER_ACTIVE; echo; cat $N/state/orch/owner_active_state.json; echo; tail -3 $N/state/orch/owner_active.log | cut -c1-250
echo "--- body_restart.sh"; sed -n 1,70p $N/ops/body_restart.sh | cut -c1-240 | S
echo "--- known good / cmds"; ls $N/agent/autotrain | grep -iE "cmd|mode"; cat $N/agent/autotrain/mode; for f in $N/agent/autotrain/donor_hybrid.cmd*; do echo "## $f"; cat $f | cut -c1-500; done
echo "--- nox_orch 8104/8105 refs"; grep -nE "8104|8105|parallel|body_restart" $N/stewards/nox_orch.py | cut -c1-220 | head -40
echo "--- 8301 log"; tail -5 $N/integration/adapter_mem_8301.log 2>/dev/null | cut -c1-250; ls $N/agent/out | grep -E "8301|8090|core" | head
echo "--- bind errors"; grep -rIlE "Address already in use|errno 98|EADDRINUSE" $N/agent/out $N/state/core $N/logs $N/svc/logs 2>/dev/null | head
