#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/nox/v7_src_v6/nox_wow
python3 - "$ROOT" <<'PY'
import json, pathlib, re, sys, collections
r=pathlib.Path(sys.argv[1])
for name in ("CORES/CORE_1M.md","CORES/SCHEMA.md","CATALOGS/CORE_SOURCES.md","SEED/core_distill.py","SPRINT3D/banks.json"):
 p=r/name
 print(f"=== {name} bytes={p.stat().st_size if p.exists() else 'MISSING'}")
 if not p.exists(): continue
 if p.suffix==".py":
  for line in p.read_text(errors="replace").splitlines():
   if re.match(r"^(def |class )",line): print(line[:180])
 elif p.suffix==".json":
  d=json.loads(p.read_text())
  arr=d if isinstance(d,list) else next((v for v in d.values() if isinstance(v,list)),[])
  print("top_keys=",list(d)[:20] if isinstance(d,dict) else "list","entries=",len(arr))
  ids=[]
  licenses=collections.Counter()
  for x in arr:
   if isinstance(x,dict):
    ids.append(str(x.get("id") or x.get("name") or x.get("dataset") or "?"))
    licenses[str(x.get("license") or x.get("license_id") or "UNSPECIFIED")]+=1
  print("sample_ids=",ids[:12])
  print("license_fields=",licenses.most_common(12))
 else:
  lines=p.read_text(errors="replace").splitlines()
  heads=[x[:180] for x in lines if re.match(r"^#{1,4} ",x)]
  print("headings="," | ".join(heads[:24]))
  if name.endswith("CORE_1M.md"):
   picks=[x.strip() for x in lines if re.search(r"1,000,000|1 000 000|level|уров|parameter|параметр|pipeline|конвейер|bank|банк|schema|схем",x,re.I) and not x.startswith("#")]
   print("plan_lines="," | ".join(picks[:20])[:1800])
print("=== local tools")
for n in ("hf","huggingface-cli","hf_transfer","rclone","duckdb","python3","jq"):
 import shutil
 print(n, bool(shutil.which(n)))
print("=== relevant existing files")
for base in ("CORES","SEED","SPRINT3D","scripts","state"):
 p=r/base
 if p.exists() and p.is_dir():
  fs=[str(x.relative_to(r)) for x in p.rglob("*") if x.is_file()]
  print(base, len(fs), "files", ";".join(fs[:18]))
PY
