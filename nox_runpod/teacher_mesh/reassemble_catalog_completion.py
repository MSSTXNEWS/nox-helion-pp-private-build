#!/usr/bin/env python3
"""Restore full NOX 1-100 catalog source snapshots from the Drive artifact ZIP parts.

This script NEVER installs packages, unpickles model data, runs downloaded code,
touches S03, overwrites NOX weights, or starts training.
"""
import argparse, hashlib, json, sys, zipfile
from pathlib import Path
TARGETS=(32,33,70,74,77,78)

def extract_one(zf,basename):
    names=[n for n in zf.namelist() if not n.endswith("/") and Path(n).name==basename]
    if len(names)!=1:raise ValueError(f"Expected exactly one {basename}, got {names}")
    return names[0]

def verify_or_join(root, n, output, assemble=False):
    stem=f"NOX_CATALOG_{n:03d}"
    archive=root/f"{stem}_MANIFEST.zip"
    if not archive.is_file():raise FileNotFoundError(archive)
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read(extract_one(z,"PARTS_INDEX.json")))
    if manifest.get("catalog_number")!=n or manifest.get("source_status")!="DOWNLOADED_VERIFIED":
        raise ValueError(f"{stem}: invalid source manifest")
    parts=manifest["parts"]
    if not parts or len(set(p["name"] for p in parts))!=len(parts):
        raise ValueError(f"{stem}: invalid/missing parts")
    dest=output/manifest["archive_name"] if assemble else None
    temp=dest.with_name(dest.name+".partial") if dest else None
    if assemble:
        output.mkdir(parents=True,exist_ok=True)
        stream=open(temp,"wb")
    else:
        stream=None
    overall=hashlib.sha256()
    total=0
    try:
        for part in parts:
            basename=part["name"]
            idx=basename.removeprefix("piece")
            if len(idx)!=2 or not idx.isdigit():raise ValueError(f"Invalid piece name {basename}")
            path=root/f"{stem}_PART_{idx}.zip"
            if not path.is_file():raise FileNotFoundError(path)
            partsha=hashlib.sha256()
            length=0
            with zipfile.ZipFile(path) as z:
                member=extract_one(z,basename)
                if z.getinfo(member).file_size!=part["bytes"]:raise ValueError(f"Wrong size in {path}")
                with z.open(member) as f:
                    while True:
                        b=f.read(4*1024*1024)
                        if not b:break
                        partsha.update(b);overall.update(b)
                        length+=len(b);total+=len(b)
                        if stream:stream.write(b)
            if length!=part["bytes"] or partsha.hexdigest()!=part["sha256"]:
                raise ValueError(f"SHA256 failed: {path}")
        if total!=manifest["archive_bytes"] or overall.hexdigest()!=manifest["archive_sha256"]:
            raise ValueError(f"{stem}: full archive SHA256 mismatch")
        if stream:stream.close();stream=None
        if assemble:temp.replace(dest)
        print(f"PASS {stem}: {len(parts)} ZIP parts, {total:,} bytes, SHA256 {overall.hexdigest()}" +
              (f" => {dest}" if assemble else ""),flush=True)
        return {"number":n,"bytes":total,"sha256":overall.hexdigest(),"verified":True}
    finally:
        if stream:stream.close()
        if temp and temp.exists():temp.unlink()

def main():
    p=argparse.ArgumentParser(description="Reassemble verified, complete NOX catalog sources on local disk")
    p.add_argument("folder",nargs="?",default=".",help="Folder with downloaded Google Drive ZIP parts")
    p.add_argument("--assemble",action="store_true",help="Physically assemble complete TAR archives (default: verify only)")
    p.add_argument("--output",default="NOX_CATALOG_ASSEMBLED",help="Local output directory, not NOX production")
    p.add_argument("--targets",default=",".join(map(str,TARGETS)),help="Comma-separated catalog numbers")
    args=p.parse_args()
    root=Path(args.folder)
    target=[int(x.strip()) for x in args.targets.split(",") if x.strip()]
    if len(set(target))!=len(target) or any(i not in TARGETS for i in target):p.error("Invalid/duplicate target")
    failed=0
    for n in target:
        try:verify_or_join(root,n,Path(args.output),args.assemble)
        except Exception as e:failed+=1;print(f"FAIL {n}: {type(e).__name__}: {e}",file=sys.stderr)
    if failed:raise SystemExit(1)
if __name__=="__main__":main()
