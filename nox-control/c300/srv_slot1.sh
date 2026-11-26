#!/bin/bash
N=/workspace/nox
for i in 1 2 3 4 5 6; do ss -tnp 2>/dev/null | grep -E ':8104\b' | grep -v LISTEN | awk '{print $4,$5,$6}' | grep -o -E 'users:\(\("[^"]+",pid=[0-9]+' ; sleep 2; done | sort | uniq -c | sort -rn | head -12
echo == who
for p in $(ss -tnp 2>/dev/null | grep -E '127.0.0.1:8104' | grep -o -E 'pid=[0-9]+' | cut -d= -f2 | sort -u); do echo $p $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-110) age=$(ps -o etimes= -p $p); done
echo == supervisor conc; grep -n -E "concurren|max_parallel|MAX_PAR|workers|slots|nslots|donor_busy" $N/agent/nox_agents/*.py $N/agent/nox_agents/lib.py 2>/dev/null | cut -c1-170 | head -20
cat $N/state/agent_backends.json 2>/dev/null | sed -E 's/("(key|token)[^"]*": *")[^"]*/\1***/Ig' | head -c 1200
