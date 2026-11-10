#!/usr/bin/env python3
"""Copy verified 27B GGUF from A5000 ephemeral /opt into shared /workspace.
Run on A5000; do not touch source. Safe, atomic, resumable from already copied final.
"""
import argparse, hashlib, json, os, pathlib, shutil, sys, tempfile

SRC=pathlib.Path("/opt/nox_teacher_27b/Qwen3.5-27B-Q4_K_M.gguf")
RECEIPT=SRC.parent/"teacher_receipt.json"
DEST=pathlib.Path("/workspace/nox/teachers/Qwen3.5-27B")/SRC.name
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main():
    if not SRC.is_file() or not RECEIPT.is_file():
        raise SystemExit("HOLD_27B_MODEL_OR_RECEIPT_MISSING")
    r=json.loads(RECEIPT.read_text())
    if r.get("filename")!=SRC.name or not isinstance(r.get("sha256"),str):
        raise SystemExit("HOLD_27B_UNTRUSTED_RECEIPT")
    expected=r["sha256"].lower()
    if SRC.stat().st_size!=int(r.get("bytes",-1)):
        raise SystemExit("HOLD_27B_SOURCE_SIZE_MISMATCH")
    DEST.parent.mkdir(parents=True,exist_ok=True)
    # Full SHA-256 before accepting source, not just a downloaded label.
    if sha(SRC)!=expected: raise SystemExit("HOLD_27B_SOURCE_SHA_MISMATCH")
    if DEST.is_file() and DEST.stat().st_size==SRC.stat().st_size and sha(DEST)==expected:
        print("27B_SHARED_ALREADY_VERIFIED",DEST,flush=True);return
    if shutil.disk_usage(DEST.parent).free<SRC.stat().st_size+2*1024**3:
        raise SystemExit("HOLD_SHARED_DISK_CAPACITY")
    # Temporary file resides on same destination volume for atomic rename.
    pending=DEST.with_name(DEST.name+".noxpart")
    if pending.exists():
        print("PREVIOUS_PARTIAL_PRESENT_RECOPY_SAFE",pending,flush=True)
    with SRC.open("rb") as fi,pending.open("wb") as fo:
        shutil.copyfileobj(fi,fo,8*1024*1024)
        fo.flush();os.fsync(fo.fileno())
    if pending.stat().st_size!=SRC.stat().st_size or sha(pending)!=expected:
        raise SystemExit("HOLD_27B_COPY_SHA_MISMATCH")
    os.replace(pending,DEST)
    print("27B_SHARED_SHA256_VERIFIED",DEST,flush=True)

if __name__=="__main__":
    main()
