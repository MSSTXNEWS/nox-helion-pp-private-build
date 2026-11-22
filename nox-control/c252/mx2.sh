#!/bin/bash
cd /root/nox/dl/v7/exec2/nox_wow/SPD
python3 -c "
import json;m=json.load(open('matrix.json'))
for k,v in m.items():
    if not isinstance(v,list): print(k,json.dumps(v,ensure_ascii=False)[:700])
"|head -12
grep -nE 'def |Popen|kill|pgrep|8081|taskset|numactl|winner' ab_bench.py | cut -c1-150 | head -50
