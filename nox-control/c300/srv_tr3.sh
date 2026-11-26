#!/bin/bash
D=/workspace/nox/distill_v2
ls -la $D/gates | head -20; ls $D/code | head -30
grep -rln -i "gates" $D/code /workspace/nox/agent/*.py 2>/dev/null | head
sed -n 120,159p /workspace/nox/agent/autotrain/autotrain.sh | cut -c1-230
