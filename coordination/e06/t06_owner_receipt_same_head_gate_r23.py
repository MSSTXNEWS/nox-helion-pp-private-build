"""T06: verify actual Git owner-receipt objects at ONE immutable HEAD.
Source-only verifier: never emits native/Windows/SOURCE_READY acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
RECEIPTS={
    "P01":"donors/P01_C07/P01_C07_RECEIPT.json",
    "P02":"Packages/P02/evidence/P02_NATIVE_INGRESS_RECEIPT.json",
    "P03":"Packages/P03/Source/receipts/NOX_V16_E03_W3_02_R16_20261029.json",
    "P04":"Packages/P04/E04_ONEHOST_BRIDGE_RECEIPTS.json",
    "P05":"Packages/P05/E05/space/E05_SPACE_R17_OWNER_RECEIPT.json"
}
HEX40=re.compile(r"[0-9a-f]{40}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")

def git(*args):
    p=subprocess.run(["git","-C",str(ROOT),*args],capture_output=True,timeout=15)
    if p.returncode:
        raise ValueError("GIT_READ_FAILED:"+args[0])
    return p.stdout

def safe_path(value):
    """Reject unsafe Windows path components even on non-Windows QA hosts."""
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    for component in value.split("/"):
        if (component in ("", ".", "..") or component != component.rstrip(" .")
                or any(part.endswith(" ") for part in component.split("."))
                or not component.isprintable()
                or re.search(r'[<>:"|?*\x00-\x1f\x7f]', component)
                or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?',
                                component, flags=re.IGNORECASE)):
            return False
    return True

def blob_at(head,path):
    if not safe_path(path):raise ValueError("UNSAFE_OWNER_RECEIPT_PATH")
    try:
        value=git("rev-parse",head+":"+path).decode().strip()
    except ValueError:
        return None
    if not HEX40.fullmatch(value):
        return None
    try:
        return value if git("cat-file","-t",value).decode().strip()=="blob" else None
    except ValueError:
        return None

def read_at(head,path):
    if not safe_path(path):raise ValueError("UNSAFE_OWNER_RECEIPT_PATH")
    return git("show",head+":"+path)

def audit(head):
    result={"schema":"NOX_V16_OWNER_RECEIPT_SAME_HEAD_AUDIT_V1",
            "head":head,"owners":{},"host50":{},"native_windows":"NOT_RUN",
            "source_ready":False,"owner_qa_accepted":False}
    for name,path in RECEIPTS.items():
        data=json.loads(read_at(head,path))
        items=data.get("parts") if name=="P01" else (
            data.get("paths") if name=="P02" else data.get("files"))
        if not isinstance(items,list) or not items:
            raise ValueError("OWNER_RECEIPT_ROWS_MISSING:"+name)
        checks=[]
        for item in items:
            target=item.get("path")
            if not safe_path(target):
                raise ValueError("UNSAFE_OWNER_SOURCE_PATH:"+name)
            actual=blob_at(head,target)
            expected=(item.get("post_git_blob_sha1") or
                      item.get("postGitBlobSha1") or item.get("git_blob_sha1"))
            if isinstance(expected,str) and HEX40.fullmatch(expected):
                ok=actual==expected
                method="GIT_BLOB"
            elif isinstance(item.get("sha256"),str) and HEX64.fullmatch(item["sha256"]):
                try:
                    ok=hashlib.sha256(read_at(head,target)).hexdigest()==item["sha256"]
                except ValueError:
                    ok=False
                method="SHA256_BYTES"
            else:
                ok=False
                method="UNSUPPORTED_OWNER_RECEIPT_DIGEST"
            checks.append({"path":target,"method":method,
                           "actual":actual,"expected":expected or item.get("sha256"),
                           "match":bool(ok)})
        result["owners"][name]={"receipt_path":path,
                "receipt_blob":blob_at(head,path),"checked":len(checks),
                "matched":sum(int(x["match"]) for x in checks),
                "all_match":all(x["match"] for x in checks),
                "exceptions":[x for x in checks if not x["match"]]}
    mapping=json.loads(read_at(head,"proposals/NOX-PACK01-50/owner-binding-map.json"))
    routes=mapping["routes"]
    result["host50"]={
        "map_blob":blob_at(head,"proposals/NOX-PACK01-50/owner-binding-map.json"),
        "routes":len(routes),
        "source_bound":sum(bool(x.get("sourceBinding")) for x in routes),
        "source_unbound":[x["routeId"] for x in routes if not x.get("sourceBinding")],
        "native_pending":[x["routeId"] for x in mapping["remainingNativeBlockers"]],
        "windows_runtime_verified":False}
    result["all_source_receipts_match"]=all(v["all_match"] for v in result["owners"].values())
    result["status"]="SOURCE_RECEIPT_MATCH" if result["all_source_receipts_match"] else "STALE_OWNER_RECEIPTS"
    result["status"]+="_NATIVE_NOT_ACCEPTED"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--expected-head",required=True)
    args=p.parse_args()
    head=git("rev-parse","HEAD").decode().strip()
    if not HEX40.fullmatch(args.expected_head) or head!=args.expected_head:
        print(json.dumps({"status":"HEAD_DRIFT","actual":head,"expected":args.expected_head}))
        return 2
    try:
        report=audit(head)
    except (OSError,ValueError,UnicodeError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc)[:120]}))
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    # This is only source receipt audit; NEVER a native success receipt.
    return 0 if report["all_source_receipts_match"] else 2

if __name__=="__main__":
    sys.exit(main())
