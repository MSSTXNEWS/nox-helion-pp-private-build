#!/bin/bash
date -u +%T; ls -l /dev/shm/glm53f/*00005* | cut -c20-90; tail -1 /root/nox/logs/flash.log|cut -c1-100
D=/root/nox/dl/v7/core/nox_wow
wc -l $D/TOP/eval_top.py $D/MIND/M4_BENCH/mind_bench.py $D/WOW/voice_bench.py $D/MIND/M4_BENCH.md
grep -n "^def \|^[A-Z_]* *= *[\[{(]" $D/TOP/eval_top.py | head -20
grep -n "^def \|^[A-Z_]* *= *[\[{(]" $D/MIND/M4_BENCH/mind_bench.py | head -20
grep -n "^def \|^[A-Z_]* *= *[\[{(]" $D/WOW/voice_bench.py | head
ls /root/nox/state/MODEL_SWAP | head; ls /root/nox/*.json /root/nox/*.jsonl 2>/dev/null | head
