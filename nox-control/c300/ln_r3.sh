echo "K1: ln_r3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
P=$(ss -ltnp | grep ':8091 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "8091 pid $P"; tr '\0' ' ' </proc/$P/cmdline | cut -c1-200; echo; ls -l /proc/$P/cwd | sed 's/.*-> //'
Q=$(ss -ltnp | grep ':18220 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "18220 pid $Q"; tr '\0' ' ' </proc/$Q/cmdline | cut -c1-200; echo; ps -o ppid=,etime= -p $Q
tail -c 600 $N/svc/logs/mem.log | grep -v extract | cut -c1-200
WS=$(ls $N/web/pkg/server/*.py | head -5); echo $WS
echo "== routes"; grep -hoE "'/(api|svc|memory|glm|img|health|outbox)[A-Za-z0-9_/.{}<>-]*'" $N/web/pkg/server/*.py 2>/dev/null | sort -u | head -150 | tr '\n' ' '
echo; echo "== svc routes"; grep -n "nox-living\|/svc/" $N/web/pkg/server/*.py | head -8 | cut -c1-180
echo "== caddyfile"; grep -E "handle|reverse_proxy|route" /etc/caddy/Caddyfile $N/ops/*/Caddyfile 2>/dev/null | head -30 | cut -c1-140
echo "== page list"; D=$(ls -d $N/web/deploy* $N/web/pkg/deploy 2>/dev/null | head -3); echo $D
find $N/web -name 'chat-dc.html' -not -path '*/node_modules/*' | head
echo "== guard procs"; pgrep -af disk_guard | cut -c1-120
crontab -l | grep -E "disk_guard|backup|selfheal|canon|inner" | cut -c1-160
