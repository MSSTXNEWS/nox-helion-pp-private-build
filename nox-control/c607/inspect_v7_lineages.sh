#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import hashlib, json
roots = {
    "V6_TREE": Path("/root/nox/v7_src_v6/nox_wow"),
    "FLASH": Path("/root/nox/in_flash/NOX_S1_FLASH_OPTIM_EXEC_FULL_20261122"),
    "FLASH_BASE": Path("/root/nox/in_flash/NOX_S1_FLASH_OPTIM_EXEC_FULL_20261122/02_UNIFIED_BASE"),
    "WOW7_BRAIN": Path("/root/nox/src/wow7/brain"),
    "V7_04": Path("/root/nox/backups/v7/V7-04"),
    "STATE_V7": Path("/root/nox/state/v7"),
}
def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()
maps={}
for label, root in roots.items():
    fs=files(root)
    maps[label]={str(p.relative_to(root)):digest(p) for p in fs}
    total=sum(p.stat().st_size for p in fs)
    th=hashlib.sha256()
    for rel in sorted(maps[label]):
        th.update(rel.encode()); th.update(b"\0"); th.update(maps[label][rel].encode()); th.update(b"\n")
    print(f"ROOT|{label}|{root}|{len(fs)}|{total}|TREE={th.hexdigest()[:16]}")
print("-- TOPLEVEL FLASH --")
for p in sorted(roots["FLASH"].iterdir()) if roots["FLASH"].is_dir() else []:
    print(("DIR" if p.is_dir() else "FILE")+"|"+p.name)
print("-- LATE BRAIN FILES --")
for rel,sha in maps["WOW7_BRAIN"].items():
    p=roots["WOW7_BRAIN"]/rel
    print(f"{sha[:16]}|{p.stat().st_size}|{rel}")
print("-- V6 VS FLASH BASE --")
a,b=maps["V6_TREE"],maps["FLASH_BASE"]
same=sum(a[k]==b[k] for k in a.keys() & b.keys())
changed=sum(a[k]!=b[k] for k in a.keys() & b.keys())
print(f"same={same}|changed={changed}|v6_only={len(a.keys()-b.keys())}|flash_only={len(b.keys()-a.keys())}")
print("-- V7 MANIFESTS/READMES --")
for label in ("FLASH","FLASH_BASE","V7_04","STATE_V7"):
    root=roots[label]
    for p in files(root):
        n=p.name.lower()
        if not any(x in n for x in ("manifest","sha256","readme","version","canonical","release","build")): continue
        rel=str(p.relative_to(root))
        print(f"META|{label}|{rel}|{p.stat().st_size}|{digest(p)[:16]}")
        if p.stat().st_size <= 40000 and any(x in n for x in ("readme","manifest","version","canonical","release","build")):
            try:
                lines=p.read_text(errors="replace").splitlines()
                chosen=[x.strip() for x in lines if any(k in x.lower() for k in ("canonical","version","sha256","manifest","runtime","build","v7","source","parent","base"))][:3]
                for line in chosen: print("TXT|"+line[:150])
            except Exception: pass
PY
