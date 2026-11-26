#!/bin/bash
cd /workspace/nox/brain/SLP; /workspace/nox/venv/bin/python -I - <<'PY'
import importlib.util
sp=importlib.util.spec_from_file_location("fc","/workspace/nox/brain/SLP/fidelity_cases.py"); fc=importlib.util.module_from_spec(sp); sp.loader.exec_module(fc)
print([a for a in dir(fc) if not a.startswith("_")])
for a in dir(fc):
    v=getattr(fc,a)
    if isinstance(v,(list,tuple)) and v: print(a,len(v),str(v[0])[:300])
PY
grep -n "persona" /workspace/nox/distill_v2/code/distill_v2.py | grep -i -E "def |open|path|PERSONA" | head -6 | cut -c1-200
ls /workspace/nox/brain/SLP | head -20
