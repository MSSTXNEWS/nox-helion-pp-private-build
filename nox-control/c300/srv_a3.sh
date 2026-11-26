#!/bin/bash
echo == supervisors; pgrep -af "nox_agents/supervisor.py|nox_agents.py" | cut -c1-140; ps -o pid,etimes,args -p $(pgrep -f "supervisor.py" | tr '\n' ',' | sed 's/,$//') | cut -c1-110
echo == cascade watchdog; cat /workspace/nox/agent/cascade_watchdog.sh | head -30 | cut -c1-200
pgrep -af "cascade" | cut -c1-120 | head
echo == 8400 listener; ss -tlnp | grep ':8400 ' | cut -c1-120
echo == web invoke_draw err times; grep -a -n "No module named 'invoke_draw'" /workspace/nox/agent/out/web_server.log | tail -2 | cut -c1-80; grep -a -c "" /workspace/nox/agent/out/web_server.log
echo == embed callers; for i in 1 2 3; do ss -tnp | grep ':8082 ' | grep -v LISTEN | awk '{print $5}' | sed 's/.*://' ; done | sort | uniq -c | sort -rn | head -3
for sp in $(ss -tn state established '( dport = :8082 )' | awk 'NR>1{print $4}' | sed 's/.*://' | sort -u | head -8); do o=$(ss -tnp state established "( sport = :$sp )" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$o" ] && echo "caller pid $o $(tr '\0' ' ' </proc/$o/cmdline | cut -c1-100) age=$(ps -o etimes= -p $o)"; done
tail -3 /workspace/nox/agent/out/embed_8082.log | cut -c1-160
echo == disk; du -xsh /workspace/nox/* 2>/dev/null | sort -rh | head -12
