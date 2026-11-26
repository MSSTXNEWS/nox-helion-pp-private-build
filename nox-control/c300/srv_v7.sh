#!/bin/bash
F=/workspace/nox/judges/judge_service.py
grep -n "CHEAP_CPU" $F | head -3 | cut -c1-400
curl -s -m4 127.0.0.1:8300/judges | python3 -c "
import sys,json
d=json.load(sys.stdin); d=d.get('judges',d)
for k,v in d.items():
    if v.get('status')=='загружен': print(k.split('/')[-1][:46], v.get('device'), v.get('kind'), v.get('deep'))"
