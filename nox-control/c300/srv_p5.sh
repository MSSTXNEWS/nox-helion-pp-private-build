#!/bin/bash
pgrep -f ops/p3_persona_gen.py >/dev/null && { echo already running; exit 0; }
setsid -f nice -n 10 /workspace/nox/venv/bin/python -I /workspace/nox/ops/p3_persona_gen.py 900 > /workspace/nox/state/p3/persona_gen.out 2>&1 < /dev/null
sleep 60; cat /workspace/nox/state/p3/persona_gen.out | tail -3; cat /workspace/nox/state/p3/persona_gen.json 2>/dev/null; ls /workspace/nox/distill_v2/raw_skill_p3_persona_* 2>/dev/null
