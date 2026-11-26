#!/bin/bash
F=$(find /workspace/nox -name fidelity_test.py -not -path "*/bak*" 2>/dev/null | head -1); echo $F; wc -l $F
grep -n -E "rename|flattery|false_memory" $F | head -12 | cut -c1-220
python3 -I - <<PY
import sys,importlib.util,json
sys.path.insert(0,"$(dirname $F)")
spec=importlib.util.spec_from_file_location("ft","$F"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print([a for a in dir(m) if not a.startswith("_")][:40])
PY
ls /workspace/nox/soul* /workspace/nox/state/soul* 2>/dev/null | head; ls /workspace/nox/ops | grep -i -E "fidel|persona|soul|canon" | head
