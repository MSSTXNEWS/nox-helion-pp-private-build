#!/usr/bin/env python3
"""Recover exactly the 15 verified original SOURCE ZIPs from GitHub Actions 42023301530.
No installer is executed. A source ZIP is not an installed engine.
Requires Python 3 and authenticated GitHub CLI (gh) when --artifact-dir is absent.
"""
import argparse, hashlib, json, re, subprocess, tempfile, zipfile, os, stat
from pathlib import PurePosixPath
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def safe_owner_path(p, missing=False):
    for part in (p,*p.parents):
        try: info=part.lstat()
        except FileNotFoundError:
            if missing: continue
            return False
        if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400 or getattr(part,"is_junction",lambda:False)():
            return False
    return True

def source_zip_verified(path, name):
    with zipfile.ZipFile(path) as z:
        rows=z.infolist()
        if not 1<=len(rows)<=500000:raise ValueError("Unbounded ZIP entries "+name)
        seen=set();expanded=0
        for item in rows:
            member=item.filename
            q=PurePosixPath(member)
            if not member or member.startswith(("/",chr(92))) or chr(92) in member or ":" in member or any(bit in (".","..") for bit in q.parts):
                raise ValueError("Unsafe source path "+name)
            key=member.casefold()
            if key in seen:raise ValueError("Duplicate ZIP entry "+name)
            seen.add(key);expanded+=item.file_size
            if expanded>8*1024*1024*1024:raise ValueError("Expanded ZIP too large "+name)
        if z.testzip() is not None:raise ValueError("ZIP CRC mismatch "+name)

def recover(root, out, manifest):
    results=[]
    if not safe_owner_path(root) or not safe_owner_path(out,missing=True):raise ValueError('Untrusted source or destination')
    out.mkdir(parents=True,exist_ok=True)
    for entry in manifest["engines"]:
        prefix=entry["artifact_prefix"]; name=prefix+"_ORIGINAL_SOURCE.zip"
        md=root/(prefix+"_META")
        if not md.is_dir() or not safe_owner_path(md):raise ValueError("Missing metadata: "+prefix)
        def read(n):
            p=md/n
            if not p.is_file() or not safe_owner_path(p) or p.stat().st_size>8192:raise ValueError("Bad META "+n)
            return p.read_text(encoding="utf-8-sig").strip()
        if int(read("PART_COUNT.txt"))!=entry["parts"]:raise ValueError("Wrong part count "+prefix)
        source=read("SOURCE.txt")
        if source.strip()!=("repository="+entry["upstream"]+"\ncommit="+entry["commit"]+"\narchive="+name):
            raise ValueError("Wrong source provenance "+prefix)
        checksum=read("SHA256SUMS.txt")
        if checksum!=entry["sha256"]+"  out/"+name:raise ValueError("SHA pin changed "+prefix)
        if read("VERIFIED.txt")!="PASS validated upstream zip; all parts accounted; recombined bytes identical":raise ValueError("Upstream verification missing "+prefix)
        dest=out/name
        if not safe_owner_path(dest,missing=True):raise ValueError("Unsafe target "+prefix)
        if dest.exists():
            if not safe_owner_path(dest) or not dest.is_file() or sha256(dest)!=entry["sha256"]:
                raise ValueError("Existing ZIP mismatch "+prefix)
        else:
            part=dest.with_suffix(".partial")
            if part.exists():raise ValueError("Unowned partial file "+prefix)
            total=0
            try:
                with part.open("xb") as result:
                    for i in range(entry["parts"]):
                        source=root/(prefix+f"_PART_{i:03d}")/(prefix+f".zip.part-{i:03d}")
                        if not source.is_file() or not safe_owner_path(source):raise ValueError("Missing part "+str(i))
                        with source.open("rb") as f:
                            for data in iter(lambda:f.read(4*1024*1024),b""):
                                total+=len(data)
                                if total>2_500_000_000:raise ValueError("Unbounded archive")
                                result.write(data)
                if sha256(part)!=entry["sha256"]:raise ValueError("SHA mismatch "+prefix)
                source_zip_verified(part,prefix)
                if dest.exists() or not safe_owner_path(dest,missing=True):
                    raise ValueError("Destination race "+prefix)
                os.link(part,dest)  # Exclusive: never overwrite foreign data.
            except BaseException:
                part.unlink(missing_ok=True)
                raise
        results.append({"name":entry["name"],"sha256":entry["sha256"],"bytes":dest.stat().st_size,"status":"VERIFIED_SOURCE_ONLY"})
        print(prefix,"VERIFIED_SOURCE_ONLY",flush=True)
    (out/"NOX_ENGINE15_SOURCE_RECEIPT.json").write_text(json.dumps({"run_id":manifest["run_id"],"engines":results,"installed":False,"e07":False},indent=2)+"\n",encoding="utf-8")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--artifact-dir",type=Path)
    a.add_argument("--output",type=Path,default=Path("NOX_ENGINE15_VERIFIED"))
    a.add_argument("--manifest",type=Path,default=Path(__file__).with_name("NOX_ENGINE15_SOURCELOCK_42023301530.json"))
    v=a.parse_args()
    manifest=json.loads(v.manifest.read_text(encoding="utf-8"))
    if manifest.get("run_id")!=42023301530 or len(manifest.get("engines",[]))!=15:raise ValueError("Invalid pinned run")
    if v.artifact_dir:recover(v.artifact_dir.resolve(strict=True),v.output,manifest)
    else:
        with tempfile.TemporaryDirectory(prefix="nox_engine15_") as temp:
            proc=subprocess.run(["gh","run","download","42023301530","--repo","MSSTXNEWS/nox-helion-pp-private-build","--dir",temp],check=False,timeout=900)
            if proc.returncode:raise SystemExit("GitHub download failed")
            recover(Path(temp),v.output,manifest)
if __name__=="__main__":main()
