"""V132: deterministic source-only ZIP, original Windows receiver co-located.

Whitelisted sources, SHA manifest, no secrets/weights/private user records.
Archives are not a native deployment or a release-acceptance receipt.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import zipfile

NAME="NOX_HELION_V132_ONEPASS_SAFE_SOURCE_20261115.zip"
STAMP=(2026,11,15,0,0,0)
PATHS=(
 ("nox_runpod/teacher_mesh/v132/README_RU.md","README_RU.md"),
 ("nox_runpod/teacher_mesh/v132/onepass_release_gate.py","source/v132/onepass_release_gate.py"),
 ("nox_runpod/teacher_mesh/v132/build_source_bundle.py","source/v132/build_source_bundle.py"),
 ("nox_runpod/teacher_mesh/v132/tests/test_onepass_release_gate.py","source/v132/tests/test_onepass_release_gate.py"),
 ("nox_runpod/teacher_mesh/v130/owner_s03_fact_write.py","source/v130/owner_s03_fact_write.py"),
 ("nox_runpod/teacher_mesh/v130/install_native_owner_fact.py","source/v130/install_native_owner_fact.py"),
 ("nox_runpod/teacher_mesh/v130/tests/test_owner_s03_fact_write.py","source/v130/tests/test_owner_s03_fact_write.py"),
 ("nox_runpod/teacher_mesh/v130/tests/test_install_native_owner_fact.py","source/v130/tests/test_install_native_owner_fact.py"),
 ("nox_runpod/teacher_mesh/v131/vast_no_billing_inventory.py","source/v131/vast_no_billing_inventory.py"),
 ("nox_runpod/teacher_mesh/v61/restore_offsite_chunks.py","source/v61/restore_offsite_chunks.py"),
 ("nox_runpod/teacher_mesh/v71/disk_budget.py","source/v71/disk_budget.py"),
 ("nox_runpod/teacher_mesh/v41/training/no_loss_acceptance.py","source/v41/no_loss_acceptance.py"),
 ("coordination/NOX_WEB_V293_92_ROUTE_HOST_PLAN.json","source/WEB_V293_92_ROUTE_HOST_PLAN.json"),
 ("nox_runpod/teacher_mesh/v70/NOX_V70_ONEPASS_PC.cmd","Windows_Offsite/NOX_V70_ONEPASS_PC.cmd"),
 ("nox_runpod/teacher_mesh/v70/NOX_V70_PC_ALL_ONEPASS.ps1","Windows_Offsite/NOX_V70_PC_ALL_ONEPASS.ps1"),
 ("nox_runpod/teacher_mesh/v66/windows_offsite_receiver.ps1","Windows_Offsite/windows_offsite_receiver.ps1"),
 ("nox_runpod/teacher_mesh/v70/README_RU.md","Windows_Offsite/ORIGINAL_V70_README_RU.md"),
)
MANIFEST="MANIFEST_SHA256.json"
RECEIPT="NOX_V132_ONEPASS_RECEIPT.json"

def _digest(raw:bytes)->str:
    return sha256(raw).hexdigest()

def _member(name:str,raw:bytes):
    info=zipfile.ZipInfo(filename=name,date_time=STAMP)
    info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=0o100644<<16
    return info,raw

def build(root:Path,output:Path,source_receipt:Path)->dict:
    root=Path(root)
    output=Path(output)
    if output.exists():raise ValueError("HOLD_BUNDLE_OUTPUT_EXISTS")
    receipt=json.loads(Path(source_receipt).read_text(encoding="utf8"))
    if (receipt.get("schema")!="NOX_V132_ONEPASS_SOURCE_ACCEPTANCE_V1" or
        receipt.get("release",{}).get("state")!="HOLD_REQUIRED_LIVE_ACCEPTANCE"):
        raise ValueError("HOLD_UNVERIFIED_OR_FALSE_RELEASE_RECEIPT")
    chosen=[];meta=[]
    names=set()
    for origin,target in PATHS:
        source=root/origin
        if (not source.is_file() or source.is_symlink() or
            source.stat().st_size>5_000_000 or source.stat().st_size==0):
            raise ValueError("HOLD_BUNDLE_SOURCE_UNAVAILABLE")
        if target in names or target.startswith("/") or ".." in Path(target).parts or "\\" in target:
            raise ValueError("HOLD_BUNDLE_TRAVERSAL_OR_DUPLICATE")
        names.add(target)
        b=source.read_bytes()
        chosen.append((target,b))
        meta.append({"name":target,"source_repo_path":origin,"bytes":len(b),"sha256":_digest(b)})
    windows={x for x in names if x.startswith("Windows_Offsite/")}
    required={"Windows_Offsite/NOX_V70_ONEPASS_PC.cmd",
              "Windows_Offsite/NOX_V70_PC_ALL_ONEPASS.ps1",
              "Windows_Offsite/windows_offsite_receiver.ps1"}
    if not required.issubset(windows):
        raise ValueError("HOLD_WINDOWS_RECEIVER_NOT_COLOCATED")
    receipt_bytes=(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    manifest={"schema":"NOX_V132_SHA_SOURCE_BUNDLE_V1","release_state":"SOURCE_ONLY_HOLD_LIVE",
              "onehost_instance_id":60509551,
              "original_frozen_web_sha256":receipt["web_baseline"]["frozen_zip_sha256"],
              "source_count":len(chosen),"members":meta,
              "receipt_sha256":_digest(receipt_bytes),
              "original_weights_included":False,"private_records_included":False,
              "windows_owner_restore_verified":False}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9,allowZip64=False) as z:
        for filename,content in sorted(chosen,key=lambda a:a[0]):
            z.writestr(*_member(filename,content))
        z.writestr(*_member(MANIFEST,manifest_bytes))
        z.writestr(*_member(RECEIPT,receipt_bytes))
    return verify(output)

def verify(path:Path)->dict:
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError("HOLD_BUNDLE_CRC")
        names=z.namelist()
        if len(names)!=len(set(names)) or MANIFEST not in names or RECEIPT not in names:
            raise ValueError("HOLD_BUNDLE_MEMBERS")
        manifest=json.loads(z.read(MANIFEST))
        if manifest.get("schema")!="NOX_V132_SHA_SOURCE_BUNDLE_V1":
            raise ValueError("HOLD_BUNDLE_MANIFEST")
        members=manifest.get("members")
        if not isinstance(members,list) or len(members)!=manifest.get("source_count"):
            raise ValueError("HOLD_BUNDLE_COUNT")
        expected={r["name"] for r in members}|{MANIFEST,RECEIPT}
        if set(names)!=expected:raise ValueError("HOLD_BUNDLE_EXTRA_FILE")
        if any(".." in Path(n).parts or "\\" in n or n.startswith("/") for n in names):
            raise ValueError("HOLD_BUNDLE_UNSAFE_NAME")
        for r in members:
            if _digest(z.read(r["name"]))!=r["sha256"] or len(z.read(r["name"]))!=r["bytes"]:
                raise ValueError("HOLD_BUNDLE_MEMBER_HASH")
        if _digest(z.read(RECEIPT))!=manifest["receipt_sha256"]:
            raise ValueError("HOLD_BUNDLE_RECEIPT_SHA")
        if manifest.get("release_state")!="SOURCE_ONLY_HOLD_LIVE" or manifest.get("original_weights_included") is not False:
            raise ValueError("HOLD_BUNDLE_MISLEADING_RELEASE")
    return {"state":"SOURCE_BUNDLE_SHA_CRC_VERIFIED",
            "file":path.name,"bytes":path.stat().st_size,
            "sha256":_digest(path.read_bytes()),"source_members":len(members),
            "windows_receiver_colocated":True,"production_deployed":False}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--receipt",type=Path,default=Path("nox_v132_onepass_receipt.json"))
    ap.add_argument("--output",type=Path,default=Path(NAME))
    args=ap.parse_args()
    result=build(args.root,args.output,args.receipt)
    print("NOX_V132_BUNDLE="+json.dumps(result,sort_keys=True,separators=(",",":")))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
