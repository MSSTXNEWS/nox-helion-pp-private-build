#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/root/nox/v7_src_v6/nox_wow/SPRINT3D/banks.json")
d=json.loads(p.read_text())
print("top-level",list(d))
for b in d.get("banks",[]):
 print(json.dumps({k:b.get(k) for k in ("id","repo","dataset","path","revision","config","split","license","license_id","role") if k in b},ensure_ascii=False,sort_keys=True))
PY