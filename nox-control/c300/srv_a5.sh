#!/bin/bash
for p in 2715440 74194; do echo "$p ppid=$(ps -o ppid= -p $p) etimes=$(ps -o etimes= -p $p) $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-80)"; done
tail -4 /workspace/nox/agent/out/cascade_watchdog.log | cut -c1-160
grep -a -c "address already in use" /workspace/nox/agent/out/cascade_8400.log
tail -c 20000 /workspace/nox/agent/out/cascade_8400.log | grep -a -c "address already in use"
pgrep -af "cascade_watchdog" | cut -c1-120
ls -la /workspace/nox/state/agents/ | head -8; tail -3 /workspace/nox/agent/out/nox_agents.log | cut -c1-200
grep -a "status.json.tmp" /workspace/nox/agent/out/nox_agents.log | tail -2 | cut -c1-160
