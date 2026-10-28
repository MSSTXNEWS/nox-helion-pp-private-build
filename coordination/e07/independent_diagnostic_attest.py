#!/usr/bin/env python3
"""E07 read-only attestation of ONE frozen Windows diagnostic installer.

This is intentionally NOT final product QA. It does not launch installers,
read user data, execute external code, approve GPU weights or change EXE files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

PINNED = {
    "run_id": 40611423342,
    "artifact_id": 12782319970,
    "source_sha1": "87faa41b1602a94d8f981c2a872d36c568a95039",
    "installer_sha256": "03e026141854a7dada0c94db9066f31d7f9345ca7e35a37f7a73efa9e1657310",
    "d02_sha256": {
        "Assets/home.png": "382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",
        "Assets/menu.png": "4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9",
        "Assets/core01.png": "343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97",
        "Assets/menu_sections.png": "7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4",
    }
}
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as fp:
        for b in iter(lambda:fp.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def verify(root:Path):
    if root.is_symlink() or not root.is_dir():raise ValueError("AUDIT_ROOT_NOT_REGULAR")
    found=list(root.rglob("NOX-HELION-Setup-CANDIDATE.exe"))
    if len(found)!=1 or found[0].is_symlink() or not found[0].is_file():
        raise ValueError("EXACT_ONE_FROZEN_INSTALLER_REQUIRED")
    setup=found[0]
    if setup.stat().st_size != 60497956:raise ValueError("INSTALLER_SIZE_NOT_FROZEN")
    digest=sha(setup)
    if digest!=PINNED["installer_sha256"]:raise ValueError("INSTALLER_SHA256_MISMATCH")
    with setup.open("rb") as f:header=f.read(2)
    if header!=b"MZ":raise ValueError("INSTALLER_NOT_WINDOWS_PE")

    def single(name):
        rows=list(root.rglob(name))
        if len(rows)!=1 or rows[0].is_symlink() or not rows[0].is_file():
            raise ValueError("EXACT_ONE_RECEIPT_REQUIRED:"+name)
        if rows[0].stat().st_size>4*1024*1024:
            raise ValueError("RECEIPT_SIZE_EXCEEDED:"+name)
        doc=json.loads(rows[0].read_text(encoding="utf-8-sig"))
        if not isinstance(doc,dict):raise ValueError("INVALID_RECEIPT:"+name)
        return doc

    native=single("nsis-native-transaction-qa.json")
    if any(native.get(k)!="PASS" for k in
           ("install","update","rollback","uninstall","userDataRetained")):
        raise ValueError("ORIGINAL_NATIVE_TRANSACTION_NOT_VERIFIED")
    if native.get("releaseAllowed") is not False:
        raise ValueError("FALSE_RELEASE_AUTHORIZATION")
    payload=single("payload.sha256.json")
    if payload.get("entrypoint")!="NOX.P01.Shell.exe":
        raise ValueError("ORIGINAL_WPF_ENTRYPOINT_MISSING")
    files=payload.get("files")
    if not isinstance(files,list) or len(files)<400:
        raise ValueError("DIAGNOSTIC_PAYLOAD_INCOMPLETE")
    seen=set()
    bypath={}
    for item in files:
        if not isinstance(item,dict):raise ValueError("FILE_MANIFEST_ROW_INVALID")
        name=item.get("path")
        if not isinstance(name,str) or not name or "\\" in name or name.startswith("/") or ":" in name:
            raise ValueError("FILE_PATH_INVALID")
        parts=name.split("/")
        if any(x in ("","..",".") for x in parts):raise ValueError("FILE_PATH_TRAVERSAL")
        if name.lower() in seen:raise ValueError("FILE_PATH_CASE_COLLISION")
        seen.add(name.lower())
        if type(item.get("bytes")) is not int or item["bytes"]<0:
            raise ValueError("MANIFEST_BYTES_INVALID")
        digest=item.get("sha256")
        if not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest):
            raise ValueError("MANIFEST_SHA_INVALID")
        bypath[name]=digest
    for name,expected in PINNED["d02_sha256"].items():
        if bypath.get(name)!=expected:raise ValueError("APPROVED_D02_ASSET_HASH_MISMATCH:"+name)
    single("p01-nsis-build-receipt.json")
    single("E06-real-nsis-diagnostic.json")
    return {
        "schema":"NOX-E07-DIAGNOSTIC-ATTESTATION-v1",
        "source_run":PINNED["run_id"],
        "source_sha1":PINNED["source_sha1"],
        "artifact_id":PINNED["artifact_id"],
        "setup_sha256":digest if False else sha(setup),
        "setup_size":setup.stat().st_size,
        "payload_file_count":len(files),
        "d02_original_asset_count":len(PINNED["d02_sha256"]),
        "native_installer_lifecycle":"FROZEN_SOURCE_RECEIPT_VALIDATED",
        "source_integrity":"PASS",
        "scope":"INDEPENDENT_DIAGNOSTIC_PROVENANCE_ONLY",
        "original_python_included":False,
        "full_ollama_gpu_voice_accepted":False,
        "final_e07_release_accepted":False,
        "release":"BLOCKED",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    result=verify(args.root)
    if args.out.exists():raise ValueError("NO_RECEIPT_OVERWRITE")
    args.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("E07_DIAGNOSTIC_SHA_AND_D02_PASS",result["setup_sha256"],"files",result["payload_file_count"])
    print("E07_RELEASE_BLOCKED_REAL_AI_GPU_NOT_INCLUDED")
if __name__=="__main__":main()
