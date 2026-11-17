#!/usr/bin/env python3
"""Test-only local filesystem CLI fixture. Never contacts a remote host."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

args=sys.argv[1:]
cfg=json.loads(Path(args[args.index("--config")+1]).read_text())
store=Path(cfg["fixture_store"])
if any(k in os.environ for k in ("NOX_NOTION_TOKEN","NOX_GITHUB_TOKEN","NOX_GITLAB_TOKEN")):
    raise SystemExit(77)
def remote(s):
    return store/s.split(":",1)[1]
def metadata(p):
    return {"Path":p.name,"Size":-1 if p.is_dir() else p.stat().st_size,"IsDir":p.is_dir(),"ModTime":"2026-11-17T00:00:00Z"}

if args[0]=="lsjson":
    p=remote(args[1])
    if not p.exists():
        raise SystemExit(3)
    print(json.dumps(metadata(p) if "--stat" in args else [metadata(x) for x in sorted(p.iterdir())]))
elif args[0]=="cat":
    p=remote(args[1]);limit=int(args[args.index("--count")+1])
    with p.open("rb") as f:
        while limit>0:
            chunk=f.read(min(limit,65536))
            if not chunk:
                break
            sys.stdout.buffer.write(chunk);limit-=len(chunk)
elif args[0]=="copyto":
    src=Path(args[1]);dst=remote(args[2])
    if dst.exists() and dst.read_bytes()!=src.read_bytes():
        print("simulated private-token=DO_NOT_RETURN",file=sys.stderr)
        raise SystemExit(3)
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
else:
    raise SystemExit(4)
