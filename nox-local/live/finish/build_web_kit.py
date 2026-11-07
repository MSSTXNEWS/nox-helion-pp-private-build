"""Build a reviewed, minimal NOX LIVE source delta from pinned original payload.

Do not package weights, SQLite, trainer, user files or an alternate backend.
The original NOX_READY_01 tree is a required input at installation time.
"""
from __future__ import annotations
import argparse, io, json, zipfile, hashlib
from pathlib import Path
from patch_live import read_original, patch_source, sha256

def build(payload: Path, voice: Path, output: Path):
    files = patch_source(read_original(payload), voice)
    manifest = {
        "schema":"NOX_WEB_11_22_STAGED_V1",
        "instructions_version":"0.0.6",
        "base":"NOX_READY_01; original server.py/nox_services.py/SQLite/vendor remain untouched",
        "releaseAccepted": False,
        "modelsAndWeights":"PRESERVED_NOT_INCLUDED",
        "memory":"ORIGINAL_S03_NOT_RECREATED",
        "gpuTraining":"NO_WORKER_LAUNCH_WITHOUT_ATTESTATION",
        "files":[{"name":n,"bytes":len(b),"sha256":sha256(b)} for n,b in sorted(files.items())],
    }
    output.mkdir(parents=True,exist_ok=True)
    target=output/"NOX_WEB_11_22_SOURCE.zip"
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,body in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,7,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16
            z.writestr(info,body,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        info=zipfile.ZipInfo("NOX_WEB_STAGED_MANIFEST.json",date_time=(2026,11,7,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8"))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)+1
        for f in manifest["files"]:
            assert hashlib.sha256(z.read(f["name"])).hexdigest().upper()==f["sha256"]
    receipt={"schema":"NOX_WEB_SOURCE_BUILD_V1","file":target.name,
             "bytes":target.stat().st_size,"sha256":sha256(target.read_bytes()),
             "entryCount":len(files),"releaseAccepted":False,
             "physicalOwnerWeb":"NOT_TESTED"}
    (output/"NOX_WEB_KIT_RECEIPT.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps(receipt,indent=2))
    return receipt

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--payload",type=Path,required=True)
    p.add_argument("--voice",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    build(a.payload,a.voice,a.out)
