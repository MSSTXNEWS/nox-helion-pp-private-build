#!/bin/bash
P=/workspace/nox/state/p3
for f in persona_gen persona_gen2 persona_gen3; do echo "$f: $(cat $P/$f.json 2>/dev/null | head -c 200)"; done
pgrep -af "p3_persona_gen|p3_axis_guard" | cut -c1-90
ls /workspace/nox/distill_v2 | grep -E "p3_persona|p3_antisyc" | tr '\n' ' '; echo
L=$(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -1); echo $L; grep -a -E "скорость|шаг [0-9]+, loss" ${L}train.log | tail -3 | cut -c1-160
tail -2 /workspace/nox/agent/out/autotrain.log | cut -c1-200
cat $P/train_verdict.json | head -c 300; echo
echo load $(cat /proc/loadavg); nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
ls /workspace/nox/venv_eval 2>&1 | head -2; ls $P/eval 2>&1 | head
curl -s -m3 127.0.0.1:8793/health | head -c 60; echo; curl -s -m3 127.0.0.1:8400/health; echo; curl -s -m3 127.0.0.1:8082/health | head -c 90
