#!/usr/bin/env python3
"""Recover exactly the 15 verified original SOURCE ZIPs from GitHub Actions 42023301530.
No installer is executed. A source ZIP is not an installed engine.
Requires Python 3 and authenticated GitHub CLI (gh) when --artifact-dir is absent.
"""
import argparse, hashlib, json, re, subprocess, tempfile, zipfile
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def recover(root, out, manifest):
    results=[]
    out.mkdir(parents=True,exist_ok=True)
    for entry in manifest["engines"]:
        prefix=entry["artifact_prefix"]; name=prefix+"_ORIGINAL_SOURCE.zip"
        md=root/(prefix+"_META")
        if not md.is_dir():raise ValueError("Missing metadata: "+prefix)
        def read(n):
            p=md/n
            if not p.is_file() or p.is_symlink() or p.stat().st_size>8192:raise ValueError("Bad META "+n)
            return p.read_text(encoding="utf-8-sig").strip()
        if int(read("PART_COUNT.txt"))!=entry["parts"]:raise ValueError("Wrong part count "+prefix)
        source=read("SOURCE.txt")
        if "repository="+entry["upstream"] not in source or "commit="+entry["commit"] not in source or "archive="+name not in source:
            raise ValueError("Wrong source provenance "+prefix)
        checksum=read("SHA256SUMS.txt")
        if checksum.split()[0]!=entry["sha256"] or not checksum.endswith("out/"+name):raise ValueError("SHA pin changed "+prefix)
        if "PASS" not in read("VERIFIED.txt"):raise ValueError("Upstream producer not verified "+prefix)
        dest=out/name
        if dest.exists():
            if dest.is_symlink() or not dest.is_file() or sha256(dest)!=entry["sha256"]:
                raise ValueError("Existing ZIP mismatch "+prefix)
        else:
            part=dest.with_suffix(".partial")
            if part.exists():raise ValueError("Unowned partial file "+prefix)
            total=0
            try:
                with part.open("xb") as result:
                    for i in range(entry["parts"]):
                        source=root/(prefix+f"_PART_{i:03d}")/(prefix+f".zip.part-{i:03d}")
                        if not source.is_file() or source.is_symlink():raise ValueError("Missing part "+str(i))
                        with source.open("rb") as f:
                            for data in iter(lambda:f.read(4*1024*1024),b""):
                                total+=len(data)
                                if total>2_500_000_000:raise ValueError("Unbounded archive")
                                result.write(data)
                if sha256(part)!=entry["sha256"]:raise ValueError("SHA mismatch "+prefix)
                with zipfile.ZipFile(part) as z:
                    if z.testzip() is not None:raise ValueError("CRC mismatch "+prefix)
                    for item in z.infolist():
                        path=Path(item.filename.replace(chr(92),"/"))
                        if path.is_absolute() or ".." in path.parts:raise ValueError("Unsafe source path "+prefix)
                part.rename(dest)
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
