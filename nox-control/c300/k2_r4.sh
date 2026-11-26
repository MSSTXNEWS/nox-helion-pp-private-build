echo "C300: k2_r4"
N=/workspace/nox; O=$N/agent/out
S(){ sed -E 's/(key|token|secret|password)([=: ]+)[A-Za-z0-9_\-]{8,}/\1\2***/Ig;s/--master-key [^ ]+/--master-key ***/g'; }
echo "--- 8301 log tail"; tail -4 $O/adapter_mem_8301.log | cut -c1-200; grep -c "already in use" $O/adapter_mem_8301.log
echo "--- core_8090 log"; grep -c "already in use" $O/core_8090.log; grep -n "already in use" $O/core_8090.log | tail -2 | cut -c1-200; ls -la --time-style=full-iso $O/core_8090.log
echo "--- starters of 8301"; grep -rIlE "adapter.py mem|adapter\.py\" mem" $N/ops $N/agent $N/stewards $N/operators $N/brain /etc/supervisor 2>/dev/null | grep -v "\.bak" | head
echo "--- starters of core 8090"; grep -rIlE "nox_core.py|core_8090" $N/ops $N/agent/*.sh $N/stewards $N/operators $N/brain/BRAIN/*.sh /etc/supervisor 2>/dev/null | grep -v "\.bak" | head -15
echo "--- supervisor nox_ops_core"; cat /etc/supervisor/conf.d/nox_ops_core.conf | S
echo "--- 8090 pid"; ps -o pid,ppid,etimes,args -p 3845931 | cut -c1-250
echo "--- watchdog/liska_alive refs"; grep -nE "8090|8301|nox_core|adapter.py" $N/operators/watchdog.sh $N/ops/claude/nox_watchdog.sh $N/agent/nox_agents/run_supervisor.sh $N/brain/BRAIN/liska_alive_services.sh 2>/dev/null | cut -c1-230 | head -30
echo "--- meili log"; tail -15 $N/svc/logs/meili.log | S | cut -c1-250
echo "--- meili starters"; grep -rIlE "meilisearch|meili" $N/ops $N/agent/*.sh $N/stewards $N/operators $N/svc/*.sh /etc/supervisor 2>/dev/null | grep -v "\.bak" | head
ls $N/svc | head -30
echo "--- gb10 tunnel script"; cat $N/ops/gb10_judge_tunnel.sh | S | cut -c1-200 | head -40
echo "--- web_chat tunnel conf + script"; cat /etc/supervisor/conf.d/nox_web_chat_tunnel.conf | S; cat $N/ops/web_chat_auth/run_tunnel.sh | S | head -20
tail -3 $O/*gb10*tunnel*.log 2>/dev/null | cut -c1-200
