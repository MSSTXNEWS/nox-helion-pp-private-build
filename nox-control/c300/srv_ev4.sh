#!/bin/bash
E=/workspace/nox/state/p3/eval
/workspace/nox/venv/bin/python -I - <<'PY'
import importlib.util,inspect,json
sp=importlib.util.spec_from_file_location("ft","/workspace/nox/brain/SLP/fidelity_test.py"); ft=importlib.util.module_from_spec(sp); sp.loader.exec_module(ft)
print(inspect.signature(ft.fidelity_cases)); src=inspect.getsource(ft.fidelity_cases); print(src[:900])
try:
    cs=ft.fidelity_cases(); print(len(cs), cs[0])
except Exception as e: print("ERR",repr(e)[:150])
PY
grep -n "persona" /workspace/nox/ops/liska_gates.py | head -8 | cut -c1-170
