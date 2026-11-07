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
    # Bundle the exact third-party MIT original to eliminate installer-time downloads.
    vendor = Path(__file__).resolve().parent / "vendor" / "radiant"
    source = (vendor / "SOURCE-eclipse-glow.html").read_bytes()
    license_text = (vendor / "LICENSE").read_bytes()
    def git_blob(data):
        return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\\0"+data).hexdigest()
    if git_blob(source) != "ef61254ca3b19830d8be6bf960e957ed613f69b0":
        raise RuntimeError("PINNED_ORIGINAL_SHADER_HOLD")
    if git_blob(license_text) != "3e54c0daeb1d1a0c462019e6fd3e96cc82651daf":
        raise RuntimeError("PINNED_SHADER_LICENSE_HOLD")
    old_label = b'<div class="label">Eclipse Glow</div>'
    if source.count(old_label)!=1 or not license_text.startswith(b"MIT License"):
        raise RuntimeError("ORIGINAL_SHADER_ID_OR_LICENSE_HOLD")
    files["vendor/radiant/SOURCE-eclipse-glow.html"] = source
    files["vendor/radiant/LICENSE"] = license_text
    files["vendor/radiant/eclipse-glow.html"] = source.replace(old_label,b"")
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
