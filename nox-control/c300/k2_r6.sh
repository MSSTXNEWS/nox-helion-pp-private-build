echo "C300: k2_r6"
N=/workspace/nox; O=$N/agent/out
S(){ sed -E 's/(key|token|secret|password)([=: ]+)[A-Za-z0-9_\-]{8,}/\1\2***/Ig;s/--master-key [^ ]+/--master-key ***/g'; }
echo "=== nox_index.py"; wc -l $N/svc/nox_index.py; cat $N/svc/nox_index.py | S | cut -c1-200 | head -60
grep -rIn "nox_index" /etc/supervisor/conf.d $N/ops/*.sh $N/agent/nox_ops/*.py $N/svc/*.sh 2>/dev/null | cut -c1-200 | head -5
echo "=== svc_selfheal 8301"; grep -n "8301\|mem" $N/agent/nox_ops/svc_selfheal.py | cut -c1-220 | head
sed -n 56,110p $N/agent/nox_ops/svc_selfheal.py | cut -c1-230
echo "=== ops_core log 8090/8301 recent"; grep -E "8301|8090|nox_core" $O/nox_ops_core.log | tail -8 | cut -c1-250
echo "=== run_supervisor.sh"; grep -nE "8301|8090|nox_core|adapter" $N/agent/nox_agents/run_supervisor.sh | cut -c1-200 | head; grep -rn "adapter.py" $N/agent/nox_agents/*.sh $N/agent/nox_agents/*.py 2>/dev/null | cut -c1-200 | head -5
echo "=== selfheal_supervisor.sh"; find $N -maxdepth 3 -name selfheal_supervisor.sh 2>/dev/null | head -2; grep -nE "8301|adapter.py" $(find $N -maxdepth 3 -name selfheal_supervisor.sh 2>/dev/null | head -1) | cut -c1-220 | head
