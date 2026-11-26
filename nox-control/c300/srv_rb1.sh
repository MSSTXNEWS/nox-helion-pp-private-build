#!/bin/bash
F=/workspace/nox/ops/liska_gates.py
sed -n 30,38p $F | cut -c1-250; sed -n 299,326p $F | cut -c1-300; sed -n 573,629p $F | cut -c1-260
cat /workspace/nox/state/gates_policy.json 2>/dev/null | head -c 1500
