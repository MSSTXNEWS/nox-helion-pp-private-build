#!/bin/bash
tail -12 /workspace/nox/agent/nox_agents/run_supervisor.sh
echo ==; grep -n "ch_golden\|ch-golden" /workspace/nox/agent/nox_agents/supervisor.py | head -5 | cut -c1-160
echo ==err; grep -a -n "status.json.tmp" /workspace/nox/agent/out/nox_agents.log | tail -1 | cut -c1-30; wc -l < /workspace/nox/agent/out/nox_agents.log
echo ==ports; for p in 8096 8098 8100 8101; do echo ":$p $(curl -s -m2 127.0.0.1:$p/health | head -c 80)"; done
ss -tlnp | grep -E "pid=(3995171|908593)" | awk '{print $4}'
grep -n "board\|/health" /workspace/nox/agents/nox_agents.py | head -5 | cut -c1-140
