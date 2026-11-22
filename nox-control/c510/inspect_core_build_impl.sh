#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/nox/v7_src_v6/nox_wow
python3 - "$ROOT" <<'PY'
import pathlib,re,sys
r=pathlib.Path(sys.argv[1])
for rel in ("SPRINT3D/sprint.py","SEED/core_distill.py","CORES/CORE_1M.md"):
 p=r/rel; lines=p.read_text(errors="replace").splitlines()
 print("==",rel,"bytes",p.stat().st_size)
 for i,s in enumerate(lines):
  if re.match(r"\s*(def .*build_core|def .*fetch_banks|def .*core|class .*Core)",s,re.I) or ("build-core" in s and "add_parser" in s):
   start=max(0,i-2); end=min(len(lines),i+58)
   for n in range(start,end): print(f"{n+1}: {lines[n][:170]}")
   print("...")
PY