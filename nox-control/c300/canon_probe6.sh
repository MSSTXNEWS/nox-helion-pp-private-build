#!/bin/bash
echo "C300: canon_probe6"
N=/workspace/nox
sed -n 18,27p $N/agent/nox_agents/sleep.py
echo "== quiet"; grep -n 'quiet\|QUIET\|23\|hour' $N/brain/COMMON/quiet.py | head -12 | cut -c1-140
grep -n 'quiet\|hour\|tick\|sleep(' $N/agent/nox_agents/life_loop.py | head -14 | cut -c1-140
grep -n 'quiet' $N/agent/nox_agents/initiative.py 2>/dev/null | head -5 | cut -c1-140
ls $N/agent/nox_agents | head -50 | tr '\n' ' '
echo; df -h /workspace | tail -1
