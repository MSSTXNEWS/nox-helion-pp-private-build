#!/bin/bash
O=/workspace/nox/ops
ls -d $O/v5_* | head; ls -la $O/v5_sycophancy36_20261125 | head -20
python3 -I - <<'PY'
import json,glob
for f in glob.glob("/workspace/nox/ops/v5_sycophancy36_20261125/*.json")[:3]:
    d=json.load(open(f)); print(f.split("/")[-1], type(d).__name__, len(d), list(d)[:3] if isinstance(d,dict) else "")
PY
grep -rn "nox_v5" /workspace/nox/distill_v2/code/distill_v2.py | head -8 | cut -c1-200
ls /workspace/nox/distill_v2 | grep -i -E "v5|persona|anti|syco"
grep -n "PREPMIX" -A12 /workspace/nox/distill_v2/code/distill_v2.py | sed -n 1,30p | cut -c1-230
