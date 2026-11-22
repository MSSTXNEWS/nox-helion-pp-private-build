#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path("/root/nox/v7_src_v6/nox_wow/SPRINT3D/RUNBOOK.md")
print("RUNBOOK bytes",p.stat().st_size)
for i,s in enumerate(p.read_text(errors="replace").splitlines()[:35],1):
 print(f"{i}: {s[:180]}")
PY