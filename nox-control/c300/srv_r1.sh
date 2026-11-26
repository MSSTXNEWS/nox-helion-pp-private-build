#!/bin/bash
for p in $(pgrep -f "nox_agents/supervisor.py|nox_agents.py|nox_agents/"); do echo "$p ppid=$(ps -o ppid= -p $p|tr -d ' ') et=$(ps -o etimes= -p $p) cwd=$(readlink /proc/$p/cwd) $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-120)"; done
ls /workspace/nox/agent/nox_agents | grep -i -E "start|run|launch|\.sh" ; ls /workspace/nox/agent | grep -i -E "start|launch|agents" | head
ls /workspace/nox/agents | head -20
grep -n "ch-golden\|ch_golden" -r /workspace/nox/agent/nox_agents/*.py 2>/dev/null | head -3 | cut -c1-150
curl -s -m3 127.0.0.1:8095/health | head -c 200; ss -tlnp | grep -E "python" | grep -E ":(18[0-9]{3}|80[89][0-9])" | awk '{print $4,$6}' | head -15
