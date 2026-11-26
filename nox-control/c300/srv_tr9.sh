#!/bin/bash
tail -8 /workspace/nox/agent/out/autotrain.log | cut -c1-220
ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -2
L=$(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -1)train.log
grep -a -E "скорость|ckpt_every|ОБУЧ|шаг [0-9]+, loss" $L | tail -6 | cut -c1-200
ps -o pid,etimes,args -p $(pgrep -f "distill_v2.py (train|gen|judge|prep)" | tr '\n' ',' | sed 's/,$//') 2>/dev/null | cut -c1-140
