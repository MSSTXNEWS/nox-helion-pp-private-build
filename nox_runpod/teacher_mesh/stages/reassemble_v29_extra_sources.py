#!/usr/bin/env python3
"""Restore or validate NOX V29 extra source-code archives from real Google Drive ZIP parts.

No downloads, installs, extraction, execution or production access.
The material is untrusted external open-source snapshots, not NOX model weights.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,sys,zipfile

SCHEMA_EXTRAS="nox-v29-source-chunks-v1"
SCHEMA_LARGE="nox-v29-oversized-pinned-source-v1"
GROUPS={
    "kernels":"NOX_V29_EXTRA_kernels",
    "benchmarks":"NOX_V29_EXTRA_benchmarks",
    "flashinfer":"NOX_V29_LARGE_flashinfer",
    "tau2":"NOX_V29_LARGE_tau2",
}
SHA=lambda s:isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s)

def member_by_basename(archive:zipfile.ZipFile,basename:str):
    names=[n for n in archive.namelist()
           if not n.endswith("/") and pathlib.PurePosixPath(n).name==basename]
    if len(names)!=1:raise ValueError("NOX_AMBIGUOUS_ARTIFACT_MEMBER_"+basename)
    return names[0]

def verify(root:pathlib.Path,group:str,*,out:pathlib.Path|None=None)->dict:
    if group not in GROUPS:raise ValueError("NOX_UNKNOWN_GROUP")
    prefix=GROUPS[group]
    index_path=root/(prefix+"_INDEX.zip")
    if not index_path.is_file() or index_path.is_symlink():
        raise FileNotFoundError(index_path)
    with zipfile.ZipFile(index_path) as z:
        if z.testzip() is not None:raise ValueError("NOX_INDEX_CRC_FAIL")
        index=json.loads(z.read(member_by_basename(z,"PARTS_INDEX.json")))
    if (index.get("group")!=group or
        index.get("schema") not in (SCHEMA_EXTRAS,SCHEMA_LARGE) or
        not SHA(index.get("archive_sha256")) or
        type(index.get("archive_bytes")) is not int or
        not 1<=index["archive_bytes"]<=700_000_000 or
        not isinstance(index.get("parts"),list) or
        not 1<=len(index["parts"])<=12):
        raise ValueError("NOX_MANIFEST_INVALID")
    if out is not None:
        if not out.is_dir():raise ValueError("NOX_OUTPUT_DIR_MUST_ALREADY_EXIST")
        target=out/(prefix+".tar")
        if target.exists():raise ValueError("NOX_NO_OVERWRITE_EXISTING_TARGET")
        temp=out/(prefix+".partial")
        if temp.exists():raise ValueError("NOX_NO_OVERWRITE_PARTIAL_TARGET")
        writer=temp.open("xb")
    else:target=None;temp=None;writer=None
    archive_sha=hashlib.sha256()
    total=0
    observed=[]
    try:
        for expected_index,part in enumerate(index["parts"]):
            basename="piece%02d"%expected_index
            if (not isinstance(part,dict) or part.get("name")!=basename or
                type(part.get("bytes")) is not int or
                not 0<part["bytes"]<=48*1024*1024 or
                not SHA(part.get("sha256"))):
                raise ValueError("NOX_INVALID_PART_INDEX")
            file=root/(prefix+"_PART_%02d.zip"%expected_index)
            if not file.is_file() or file.is_symlink():raise FileNotFoundError(file)
            h=hashlib.sha256();count=0
            with zipfile.ZipFile(file) as z:
                if z.testzip() is not None:raise ValueError("NOX_ARTIFACT_ZIP_CRC_FAIL")
                m=member_by_basename(z,basename)
                if z.getinfo(m).file_size!=part["bytes"]:
                    raise ValueError("NOX_PART_SIZE_MISMATCH")
                with z.open(m) as stream:
                    while block:=stream.read(2*1024*1024):
                        count+=len(block);total+=len(block)
                        if total>index["archive_bytes"]:raise ValueError("NOX_ARCHIVE_SIZE_EXCEEDED")
                        h.update(block);archive_sha.update(block)
                        if writer:writer.write(block)
            if count!=part["bytes"] or h.hexdigest()!=part["sha256"]:
                raise ValueError("NOX_PART_SHA256_MISMATCH")
            observed.append({"index":expected_index,"bytes":count,
                             "sha256":h.hexdigest()})
        if total!=index["archive_bytes"] or archive_sha.hexdigest()!=index["archive_sha256"]:
            raise ValueError("NOX_FULL_ARCHIVE_SHA256_MISMATCH")
        if writer:writer.close();writer=None;temp.rename(target)
        return {"group":group,"state":"FULL_SOURCE_TAR_SHA256_VERIFIED",
                "bytes":total,"sha256":archive_sha.hexdigest(),
                "pieces":len(observed),"assembled_file":str(target) if target else None,
                "code_executed":False,"no_system_changes":True}
    finally:
        if writer:writer.close()
        if temp and temp.exists():temp.unlink()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("directory",type=pathlib.Path,help="Directory with ZIP parts and INDEX ZIP")
    p.add_argument("--groups",default=",".join(GROUPS))
    p.add_argument("--assemble",type=pathlib.Path,help="Existing empty destination directory for verified TARs")
    args=p.parse_args()
    success=[];failed={}
    for group in args.groups.split(","):
        group=group.strip()
        try:
            result=verify(args.directory,group,out=args.assemble)
            success.append(result)
            print(json.dumps(result))
        except Exception as exc:
            failed[group]=type(exc).__name__+": "+str(exc)
            print(json.dumps({"group":group,"state":"HOLD","error":failed[group]}),file=sys.stderr)
    if failed:raise SystemExit(2)
if __name__=="__main__":main()
