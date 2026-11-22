#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
r=Path("/root/nox/v7_src_v6/nox_wow/SPRINT3D")
for n in ("RUNBOOK.md","PRIVACY.md","COST.md"):
 p=r/n; print("==",n,p.stat().st_size)
 for i,s in enumerate(p.read_text(errors="replace").splitlines()[:110],1):
  print(f"{i}: {s[:150]}")
PY