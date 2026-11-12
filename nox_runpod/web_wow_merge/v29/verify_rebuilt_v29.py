#!/usr/bin/env python3
"""Read-only verifier for NOX WEB V29.2, exact ZIP and every source member.

Does not execute site code, install models, touch S03, or change production.
"""
import argparse, hashlib, json, re, sys, zipfile
from pathlib import Path, PurePosixPath

SHA="3379770d33d56e501d267c2ca603d58bce0e301b2582b6585c1944d5f5ec57d0"
D02="f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17"
ENTRY_COUNT=1089
MANIFEST_COUNT=1085

def digest_stream(stream):
 h=hashlib.sha256()
 for b in iter(lambda:stream.read(1048576),b""):h.update(b)
 return h.hexdigest()

def check(path):
 if not path.is_file():raise ValueError("NOX_V29_2_ZIP_MISSING")
 with path.open("rb") as f:
  outer=digest_stream(f)
 if outer!=SHA:raise ValueError("NOX_V29_2_EXACT_ZIP_SHA_HOLD actual="+outer)
 with zipfile.ZipFile(path) as z:
  names=[n for n in z.namelist() if not n.endswith("/")]
  if len(names)!=ENTRY_COUNT:raise ValueError("NOX_V29_2_ZIP_MEMBER_COUNT_HOLD")
  if len(names)!=len(set(n.casefold() for n in names)):
   raise ValueError("NOX_V29_2_CASEFOLD_COLLISION")
  if any(not n.startswith("site/") or "\\" in n or ":" in n or
         ".." in PurePosixPath(n).parts or n.startswith("/") for n in names):
   raise ValueError("NOX_V29_2_UNSAFE_MEMBER")
  if z.testzip() is not None:raise ValueError("NOX_V29_2_ZIP_CRC_HOLD")
  manifest=json.loads(z.read("site/SOURCE_MANIFEST_V29.json"))
  receipt=json.loads(z.read("site/NOX_V29_UNIFIED_RECEIPT.json"))
  if len(manifest)!=MANIFEST_COUNT:raise ValueError("NOX_V29_2_SOURCE_MANIFEST_COUNT_HOLD")
  if receipt.get("release_accepted") is not False or receipt.get("production_modified") is not False:
   raise ValueError("NOX_V29_2_UNTRUSTED_RELEASE_RECEIPT")
  for name, item in manifest.items():
   f="site/"+name
   if f not in z.namelist():raise ValueError("NOX_V29_2_MISSING_SOURCE "+f)
   if z.getinfo(f).file_size!=item["bytes"]:raise ValueError("NOX_V29_2_SOURCE_SIZE_MISMATCH "+f)
   with z.open(f) as stream:
    if digest_stream(stream)!=item["sha256"]:
     raise ValueError("NOX_V29_2_SOURCE_HASH_MISMATCH "+f)
  with z.open("site/index.html") as data: main_hash=digest_stream(data)
  if main_hash!=D02:raise ValueError("NOX_V29_2_ORIGINAL_D02_CHANGED")
  assert b'location.replace("./chat.html")' in z.read("site/resonance.html")
  for path in ("site/pc/resonance.html","site/pc/memory.html","site/nox-v29-pc-genesis-addons.mjs",
               "site/nox-v29-pc-genesis-addons.css","site/qa/v29/test_v29_pc_api_contract.cjs"):
   if path not in z.namelist():raise ValueError("NOX_V29_2_REQUIRED_FILE_MISSING "+path)
 return {"schema":"nox-v29-2-final-offline-verify-v1",
         "status":"EXACT_SOURCE_ZIP_VERIFIED_NOT_RUNTIME",
         "archive":str(path),"bytes":path.stat().st_size,
         "sha256":outer,"crc":"PASS","entries":len(names),
         "site_manifest_sha256":"PASS "+str(len(manifest))+" entries",
         "original_d02_sha256":main_hash,
         "windows_onehost_e07":"NOT_RUN","production_modified":False}

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("archive",type=Path)
 x=p.parse_args()
 try:print(json.dumps(check(x.archive),ensure_ascii=False,indent=2))
 except Exception as e:print("NOX_V29_2_SOURCE_HOLD",str(e),file=sys.stderr);sys.exit(2)
