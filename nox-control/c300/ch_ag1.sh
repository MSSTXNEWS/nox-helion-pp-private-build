echo "C300: ch_ag1"
N=/workspace/nox; ls $N/agents | head -30; ls $N/agent/nox_agents | head -30
for f in $N/agents/nox_agents.py $N/agent/nox_agents/supervisor.py; do echo "=== $f"; wc -l $f; grep -n "cron\|schedule\|interval\|every\|periodic\|SCHED\|def tick\|period" $f | cut -c1-200 | head -25; done
ls $N/agents/*.json $N/agents/*.yaml $N/agents/*.yml $N/agent/nox_agents/*.json $N/agent/nox_agents/*.yaml 2>/dev/null | head
