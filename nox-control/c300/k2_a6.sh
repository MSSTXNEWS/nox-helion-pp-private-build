echo "C300: k2_a6"
N=/workspace/nox
P=$(ss -ltnp | grep ':8143 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); echo "8143 pid=$P"; ps -o pid,stat,rss,etimes,ppid,args -p $P | cut -c1-140
grep -n -A4 '"t_coder"' $N/stewards/orch_registry.json | grep -E "enabled|name" | head
grep -c '"enabled": false' $N/stewards/orch_registry.json
[ -n "$P" ] && { kill -CONT $P; kill $P; sleep 3; kill -9 $P 2>/dev/null; sleep 1; echo "after: $(ss -ltn | grep -c ':8143 ')"; }
sleep 30; echo "respawn check: $(ss -ltn | grep -c ':8143 ')"; free -g | sed -n 2p
