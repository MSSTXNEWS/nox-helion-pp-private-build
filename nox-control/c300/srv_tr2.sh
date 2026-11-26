#!/bin/bash
A=/workspace/nox/agent/autotrain
wc -l $A/autotrain.sh; grep -n -i -E "gate|ворот|promot|rollback|откат|ось|axis|NO_GAIN|accept|fail" $A/autotrain.sh | cut -c1-210 | head -50
ls /workspace/nox/distill_v2 | head -50; ls $A/rounds | tail -4; ls $A/rounds/r031
