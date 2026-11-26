#!/bin/bash
cat /workspace/nox/agent/nox_agents/run_supervisor.sh | cut -c1-200
grep -n "ch_golden\|ch-golden" /workspace/nox/agent/nox_agents/supervisor.py | head -5 | cut -c1-160
grep -a "status.json.tmp" /workspace/nox/agent/out/nox_agents.log | tail -1 | cut -c1-60; tail -c 600 /workspace/nox/agent/out/nox_agents.log | head -c 0; grep -a -n "FileNotFoundError" /workspace/nox/agent/out/nox_agents.log | tail -1 | cut -c1-40; wc -l /workspace/nox/agent/out/nox_agents.log
grep -rn "status.json" /workspace/nox/agents/*.py 2>/dev/null | head -3 | cut -c1-160
grep -n "\.tmp" /workspace/nox/agents/*.py 2>/dev/null | head -5 | cut -c1-160
for p in 8096 8098 8100 8101 8102; do curl -s -m2 127.0.0.1:$p/health | head -c 80; echo " :$p"; done
grep -rn "/board" /workspace/nox/agents/nox_agents.py | head -3 | cut -c1-140; ss -tlnp | grep 3995171 | awk '{print $4}'
