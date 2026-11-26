echo "C300: k2_r5"
N=/workspace/nox; O=$N/agent/out
S(){ sed -E 's/(key|token|secret|password)([=: ]+)[A-Za-z0-9_\-]{8,}/\1\2***/Ig;s/--master-key [^ ]+/--master-key ***/g'; }
ls -la --time-style=full-iso $O/adapter_mem_8301.log $O/web_chat_tunnel.log | cut -c30-200
echo "--- 8301 err times"; grep -nE "^(20[0-9-]+|\[)" $O/adapter_mem_8301.log | tail -3 | cut -c1-160; grep -c "Traceback" $O/adapter_mem_8301.log
echo "--- 8090 starters grep ops_core/ watchdog"; grep -rnE "nox_core\.py|adapter\.py.{0,6}mem|8301|8090" $N/agent/nox_ops/*.py $N/operators/*.sh $N/ops/p3_cpuset_guard.sh $N/ops/p3_excl_once.sh $N/agent/nox_agents/*.sh 2>/dev/null | cut -c1-240 | head -25
echo "--- cron lines w/ liska_alive"; grep -nE "nox_core|adapter|8090|8301|start" $N/brain/BRAIN/liska_alive_services.sh | cut -c1-200 | head -20
echo "--- web_chat tunnel log"; tail -6 $O/web_chat_tunnel.log | cut -c1-220; grep -c -iE "error|ERR" $O/web_chat_tunnel.log; cat $O/WEB_CHAT_URL.txt 2>/dev/null | head -c 100; echo
echo "--- meili errors count"; grep -c "ERROR" $N/svc/logs/meili.log; grep "ERROR" $N/svc/logs/meili.log | sed -E 's/\x1b\[[0-9;]*m//g;s/^[0-9T:.Z-]+ //' | sort | uniq -c | sort -rn | head -5 | cut -c1-200
grep -rIln "indexes/nox\|/indexes" $N/ops $N/agent $N/svc $N/brain $N/integration $N/stewards 2>/dev/null | grep -v -E "\.bak|\.log|venv" | head
echo "--- meili supervisor/cron?"; grep -rn "meili" /etc/supervisor/conf.d 2>/dev/null | head -3; sed -n 1,200p $N/svc/start_extra.sh | grep -n -i meili | S | cut -c1-200
echo "--- where is chat_core / image_service"; find $N -maxdepth 4 \( -name chat_core.py -o -name image_service.py -o -name "chat_core.py.bak_k1_fast*" \) -not -path "*/venv/*" 2>/dev/null | head
echo "--- invokeai"; ps -eo pid,etimes,args | grep -i invoke | grep -v grep | cut -c1-200
echo "--- llama-swap"; ps -o pid,args -p 107051 | cut -c1-250
