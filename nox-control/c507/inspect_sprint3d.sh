#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/nox/v7_src_v6/nox_wow
python3 - "$ROOT" <<'PY'
import pathlib, re, sys, ast, json, collections
r=pathlib.Path(sys.argv[1])
def short(name,limit=3600):
 p=r/name
 t=p.read_text(errors="replace")
 print(f"=== {name} bytes={len(t.encode())}")
 if len(t)<=limit: print(t)
 else:
  for line in t.splitlines():
   if re.match(r"^#{1,4} ",line) or re.search(r"resume|dry.?run|license|bank|donor|python3|pip install|--[a-z]|output|export|checkpoint",line,re.I):
    print(line[:200])
    if sum(1 for _ in [])>100: break
short("SPRINT3D/RUNBOOK.md",2200)
short("SPRINT3D/sprint.sh",2200)
short("SPRINT3D/prep_machine.sh",1800)
for name in ("SPRINT3D/sprint.py","SPRINT3D/donor_shim.py"):
 p=r/name; txt=p.read_text(errors="replace")
 print(f"=== {name} bytes={p.stat().st_size}")
 print("functions=",re.findall(r"^def\s+([A-Za-z0-9_]+)",txt,re.M)[:40])
 print("args=",[x.strip()[:180] for x in txt.splitlines() if "add_argument(" in x][:35])
 print("paths=",sorted(set(re.findall(r"[A-Za-z0-9_./-]*(?:/root/nox|/dev/shm|_state|output|cache)[A-Za-z0-9_./-]*",txt)))[:30])
 print("network_refs=",sorted(set(re.findall(r"https?://[^'\" )]+",txt)))[:12])
for name in ("SPRINT3D/_state/dryrun/work/work/selftest/core_sft.jsonl","SPRINT3D/_state/dryrun/work/work/selftest/core_kto.jsonl","SPRINT3D/_state/dryrun/work/work/selftest/kd_data.jsonl"):
 p=r/name
 if p.exists():
  print("dryrun",name,"bytes",p.stat().st_size,"lines",sum(1 for _ in p.open()))
PY
