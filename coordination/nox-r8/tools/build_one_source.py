#!/usr/bin/env python3
"""NOX HELION: one portable, content-deduplicated source ZIP. NO EXE BUILD.
Every Git-tracked file is represented. Duplicate bytes are stored only once.
Restore validates paths, lengths and SHA256; no owner state is touched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

SCHEMA="NOX_HELION_ONE_SOURCE_V1"
RESTORE=r'''#!/usr/bin/env python3
"""Reconstruct the Git source tree from a NOX one-source archive."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

def restore(archive, destination):
    dest=Path(destination).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("NOX_RESTORE_DESTINATION_MUST_BE_EMPTY")
    with zipfile.ZipFile(archive, "r") as z:
        index=json.loads(z.read("NOX_SOURCE_INDEX.json"))
        if index.get("schema")!="NOX_HELION_ONE_SOURCE_V1":
            raise ValueError("NOX_SOURCE_SCHEMA_INVALID")
        files=index["files"]
        if not isinstance(files, list) or len(files)<50:
            raise ValueError("NOX_SOURCE_FILESET_INVALID")
        seen=set()
        # Verify EVERYTHING before writing any file.
        for row in files:
            p=PurePosixPath(row["path"])
            if (not p.parts or p.is_absolute() or ".." in p.parts or
                any(part in ("", ".") for part in p.parts) or
                row["path"] in seen or
                (p.parts[0] in ("__pycache__", ".git"))):
                raise ValueError("NOX_SOURCE_PATH_HOLD")
            seen.add(row["path"])
            h=row["sha256"]
            if len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
                raise ValueError("NOX_SOURCE_HASH_HOLD")
            b=z.read("objects/"+h[:2]+"/"+h)
            if len(b)!=row["bytes"] or hashlib.sha256(b).hexdigest()!=h:
                raise ValueError("NOX_SOURCE_BYTE_HOLD: "+row["path"])
        dest.mkdir(parents=True,exist_ok=True)
        for row in files:
            p=dest.joinpath(*PurePosixPath(row["path"]).parts)
            p.parent.mkdir(parents=True,exist_ok=True)
            h=row["sha256"]
            b=z.read("objects/"+h[:2]+"/"+h)
            with p.open("xb") as stream:
                stream.write(b)
    print("NOX_SOURCE_RESTORED",len(files),"files to",dest)

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: python RESTORE_SOURCE.py <source.zip> <empty-dir>")
    restore(sys.argv[1],sys.argv[2])
'''

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=".")
    ap.add_argument("--out",required=True)
    ap.add_argument("--git-sha",required=True)
    a=ap.parse_args()
    root=Path(a.root).resolve()
    if len(a.git_sha)!=40 or any(c not in "0123456789abcdef" for c in a.git_sha):
        raise ValueError("NOX_GIT_SHA_HOLD")
    raw=subprocess.check_output(["git","ls-files","-z"],cwd=root)
    paths=sorted(p.decode("utf-8") for p in raw.split(b"\0") if p)
    if len(paths)<300:
        raise ValueError("NOX_SOURCE_FILESET_INCOMPLETE_HOLD")
    rows=[];seen_case=set();objects={}
    for rel in paths:
        posix=PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts or "\\\\" in rel or rel.startswith(".git/"):
            raise ValueError("NOX_UNSAFE_TRACKED_PATH: "+rel)
        folded=rel.casefold()
        if folded in seen_case:
            raise ValueError("NOX_WINDOWS_PATH_CASE_COLLISION: "+rel)
        seen_case.add(folded)
        p=root.joinpath(*posix.parts)
        if not p.is_file() or p.is_symlink():
            raise ValueError("NOX_MISSING_OR_SYMLINK_SOURCE: "+rel)
        h=digest(p)
        n=p.stat().st_size
        if h not in objects:objects[h]={"src":p,"bytes":n}
        elif objects[h]["bytes"]!=n:raise ValueError("NOX_SHA_COLLISION_HOLD")
        rows.append({"path":rel,"sha256":h,"bytes":n})
    duplicates={}
    for row in rows:
        duplicates.setdefault(row["sha256"],[]).append(row["path"])
    groups=[{"sha256":h,"paths":v} for h,v in duplicates.items() if len(v)>1]
    manifest={
        "schema":SCHEMA,"git_sha":a.git_sha,
        "file_count":len(rows),"unique_blob_count":len(objects),
        "deduplicated_byte_copies":len(rows)-len(objects),
        "unique_source_bytes":sum(x["bytes"] for x in objects.values()),
        "git_repository":"MSSTXNEWS/nox-helion-pp-private-build",
        "canonical": {
          "web_ui":"coordination/nox-r8/overrides/src/index.html",
          "native_host":"coordination/nox-r8/overrides/src/MainWindow.xaml.cs",
          "training_worker":"coordination/nox-r8/integrations/v16/P04/train_qlora.py"
        },
        "files":rows,"exact_duplicate_groups":groups,
        "excluded_external_data":"Google Drive historical archives, user PC weights, SQLite and checkpoints are not included without byte-level acquisition"
    }
    out=Path(a.out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():out.unlink()
    tmp=out.with_suffix(".part")
    try:
        with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for h,obj in sorted(objects.items()):
                z.write(obj["src"],arcname="objects/"+h[:2]+"/"+h)
            z.writestr("NOX_SOURCE_INDEX.json",json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
            z.writestr("RESTORE_SOURCE.py",RESTORE)
            z.writestr("START_HERE.txt",
              "NOX HELION ONE SOURCE - SOURCE ONLY / NO EXE\\n"
              "Git SHA: "+a.git_sha+"\n"
              "All Git-tracked files are SHA256-attested and deduplicated in objects/.\\n"
              "Restore: python RESTORE_SOURCE.py NOX_HELION_ONE_SOURCE.zip <empty-directory>\\n"
              "The original Git repository and Drive legacy archive are retained.\\n"
              "This is a source consolidation, NOT proof of full legacy functional parity or GPU training.\\n")
        with zipfile.ZipFile(tmp) as z:
            if z.testzip() is not None:
                raise ValueError("NOX_ONE_ZIP_CRC_HOLD")
            for row in rows:
                h=row["sha256"]
                b=z.read("objects/"+h[:2]+"/"+h)
                if len(b)!=row["bytes"] or hashlib.sha256(b).hexdigest()!=h:
                    raise ValueError("NOX_ONE_ZIP_SHA_HOLD")
        os.replace(tmp,out)
    finally:
        if tmp.exists():tmp.unlink()
    print(json.dumps({"archive":str(out),"git_sha":a.git_sha,
        "files":len(rows),"unique_blobs":len(objects),
        "duplicate_file_copies_removed":len(rows)-len(objects),
        "archive_bytes":out.stat().st_size,"sha256":digest(out)},sort_keys=True))
if __name__=="__main__":
    main()
