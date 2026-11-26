#!/bin/bash
D=/workspace/nox/distill_v2
ls $D | grep -E "^raw_skill_v5" | wc -l; ls $D | grep -E "^raw_skill" | grep -v ready4850 | head
head -c 900 $D/raw_skill_v5_ready4850_001.jsonl; echo
sed -n 625,665p $D/code/distill_v2.py | cut -c1-220
ls /workspace/nox/ops/v5_ready4850_20261124 | head; 
