#!/usr/bin/env python3
"""Strict read-only source blob check. Not a proof of installed weights or Windows EXE."""
import argparse, hashlib, json, pathlib, sys
F=pathlib.Path(__file__)
def verify(root):
    doc=json.loads(F.with_name("P03_PINNED_GIT_BLOBS.json").read_text(encoding="utf-8"))
    if doc.get("schema")!="NOX_EXPRESS_E03_OWNER_PINNED_V1":raise ValueError("INVALID_SCHEMA")
    seen=set(); checked=[]
    for item in doc["pins"]:
        name=item["path"]; rel=pathlib.PurePosixPath(name)
        if rel.is_absolute() or rel.as_posix()!=name or ".." in rel.parts or name.casefold() in seen:raise ValueError("AMBIGUOUS_PATH")
        seen.add(name.casefold()); path=root.joinpath(*rel.parts)
        if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent!=root.parent):raise ValueError("MISSING_OR_SYMLINK:"+name)
        data=path.read_bytes(); actual=hashlib.sha1(("blob "+str(len(data))).encode()+bytes([0])+data).hexdigest()
        override=next((x for x in doc.get("approved_overrides",[]) if x["path"]==name),None)
        if override:
            if override.get("owner")!=3 or override["pre_git_blob_sha1"]!=item["git_blob_sha1"]:raise ValueError("UNTRUSTED_OVERRIDE:"+name)
            need_bytes=override["post_bytes"];need_sha=override["post_git_blob_sha1"]
        else:need_bytes=item["bytes"];need_sha=item["git_blob_sha1"]
        if len(data)!=need_bytes or actual!=need_sha:raise ValueError("PIN_MISMATCH:"+name)
        checked.append({"path":name,"git_blob_sha1":actual,"file_sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)})
    actual={p.relative_to(root).as_posix() for p in (root/"Packages/P03/Source").rglob("*") if p.is_file()}
    expected={x["path"] for x in doc["pins"] if x["path"].startswith("Packages/P03/Source/")}
    if actual!=expected or len(expected)!=doc["source_files"]:raise ValueError("SOURCE_FILE_LOSS_OR_DRIFT")
    return {"run_id":doc["run_id"],"status":"SOURCE_VERIFIED_NOT_RELEASE","verified_count":len(checked),"paths":checked}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",type=pathlib.Path,default=F.resolve().parents[2]);ap.add_argument("--output",type=pathlib.Path);a=ap.parse_args()
    try: data=verify(a.root.resolve())
    except (ValueError,KeyError,TypeError,OSError) as ex: print("E03_HOLD",str(ex),file=sys.stderr);return 2
    if a.output:
        if a.output.exists():print("RECEIPT_EXISTS",file=sys.stderr);return 2
        a.output.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    print("E03_50_GIT_BLOBS_PASS",data["verified_count"])
    return 0
if __name__=="__main__":sys.exit(main())
