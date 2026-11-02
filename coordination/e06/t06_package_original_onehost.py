"""T06 Windows diagnostic OneHost candidate, reuse exact P01 owner NSIS.

Needs the already SHA+framed-IPC verified Python EXE job and original R11
staged sources. No second frontend, backend, RAG, or changed originals.
This is NOT E07 acceptance; user installation data must remain untouched.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re

EXPECTED_ZIP_SHA="90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"
VALIDATED_OLD_PYTHON_SHA="4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3"
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def download_artifact(relative,target):
    """Transfer same-job candidate bytes locally, never via GitLab artifact HTTP.

    Both source paths are fixed owner outputs. The receipt and binary hash are
    validated again below, prior to modifying any WPF or NSIS source.
    """
    expected={
        "work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json",
        "work/t06-manual-source-inspect/python-exe-candidate/NOX_HELION_PRIVATE_CANDIDATE.exe",
    }
    need(relative in expected,"T06_LOCAL_ARTIFACT_UNEXPECTED_PATH")
    origin=Path(__file__).resolve().parents[2]/relative
    need(origin.is_file() and not origin.is_symlink() and
         origin.resolve(strict=True).is_relative_to(Path(__file__).resolve().parents[2]),
         "T06_LOCAL_ARTIFACT_NOT_VERIFIED_OR_REDIRECTED")
    need(not target.exists() and not target.is_symlink(),
         "T06_LOCAL_DESTINATION_COLLISION")
    with origin.open("rb") as stream,target.open("xb") as dest:
        while chunk:=stream.read(1024*1024):
            dest.write(chunk)
    need(sha(origin)==sha(target),"T06_LOCAL_ARTIFACT_COPY_SHA_HOLD")

def build(root,staged):
    staged=Path(staged).resolve(strict=True)
    root=Path(root).resolve(strict=True)
    receipt_path=staged/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
    exe_path=staged/"NOX_HELION_PRIVATE_CANDIDATE.exe"
    for relative,target in (
      ("work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json",receipt_path),
      ("work/t06-manual-source-inspect/python-exe-candidate/NOX_HELION_PRIVATE_CANDIDATE.exe",exe_path)):
        download_artifact(relative,target)
    receipt=json.loads(receipt_path.read_text("utf-8"))
    candidate_sha=receipt.get("exe_sha256")
    need(receipt.get("phase")=="BUILT_AND_NATIVE_STDIO_SMOKE_PASS" and
         receipt.get("native_windows_exe_request_reply")=="PASS" and
         receipt.get("run_id_matched") is True and
         receipt.get("request_id_matched") is True and
         receipt.get("source_original_archive_sha256")=="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a" and
         type(candidate_sha) is str and re.fullmatch(r"[0-9a-f]{64}",candidate_sha) and
         type(receipt.get("exe_size")) is int and receipt["exe_size"]==exe_path.stat().st_size and
         receipt.get("original_729_unchanged") is True and
         receipt.get("release_accepted") is False,
         "T06_NATIVE_BACKEND_RECEIPT_INVALID")
    need(sha(exe_path)==candidate_sha,"T06_NATIVE_BACKEND_BINARY_SHA_HOLD")
    # WPF pins original backend SHA in a checked partial file. Only the
    # disposable staging tree receives the attested compiled Python SHA.
    partial=root/"Integration/MainWindow.NativeP02.cs"
    need(partial.is_file() and not partial.is_symlink(),"T06_ORIGINAL_NATIVE_PARTIAL_MISSING")
    body=partial.read_text("utf-8")
    current='private const string NativePythonSha = "'+VALIDATED_OLD_PYTHON_SHA+'";'
    need(body.count(current)==1,"T06_WPF_ORIGINAL_BACKEND_PIN_ANCHOR_HOLD")
    partial.write_text(body.replace(current,
        'private const string NativePythonSha = "'+candidate_sha+'";'),encoding="utf-8")
    payload=staged/"payload"
    cmd=["dotnet","publish",str(root/"NOX.P01.Shell.csproj"),
         "-c","Release","-r","win-x64","--self-contained","true",
         "-p:PublishSingleFile=false","-p:PublishTrimmed=false",
         "-o",str(payload),"--nologo","--verbosity","minimal"]
    published=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    (staged/"WPF_SELFCONTAINED_PUBLISH_LOG.txt").write_text(
        published.stdout+"\n"+published.stderr,encoding="utf-8")
    need(published.returncode==0,"T06_WPF_SELFCONTAINED_PUBLISH_HOLD")
    entry=payload/"NOX.P01.Shell.exe"
    need(entry.is_file(),"T06_WPF_NATIVE_ENTRYPOINT_MISSING")
    # Reuse the original owner assets, never synthesize faces/backgrounds.
    original_assets=root/"Assets"
    need(original_assets.is_dir() and not original_assets.is_symlink(),
         "T06_APPROVED_ORIGINAL_ASSETS_MISSING")
    for file in original_assets.rglob("*"):
        if file.is_dir():continue
        need(file.is_file() and not file.is_symlink(),"T06_REPARSE_ORIGINAL_ASSET_DENIED")
        out=payload/file.relative_to(root)
        out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists():
            need(out.is_file() and sha(out)==sha(file),
                 "T06_PUBLISHED_ASSET_SOURCE_MISMATCH")
        else:shutil.copy2(file,out)
    # The EXISTING R76 owner MENU10 integration is verified in the same
    # disposable WPF tree and the SAME published NSIS payload. Do not copy
    # another UI, overwrite approved art, or claim Windows E07 from source QA.
    megab_attestation=None
    if os.environ.get("NOX_MEGA_8_14")=="YES":
        import importlib.util
        gate_path=Path(__file__).resolve().parents[2]/"coordination/mega814/publish_onehost_payload.py"
        need(gate_path.is_file() and not gate_path.is_symlink(),
             "T06_MEGAB_R76_PUBLISHER_MISSING")
        gate_spec=importlib.util.spec_from_file_location("nox_r76_onehost_pub",gate_path)
        need(gate_spec is not None and gate_spec.loader is not None,
             "T06_MEGAB_R76_PUBLISHER_IMPORT_HOLD")
        gate=importlib.util.module_from_spec(gate_spec)
        gate_spec.loader.exec_module(gate)
        verified=gate.publish(root,payload)
        stage_proof_path=root/"Assets/mega814/MEGA814_RECEIPT.json"
        need(stage_proof_path.is_file(),
             "T06_MEGAB_R76_STAGE_RECEIPT_MISSING")
        stage_proof=json.loads(stage_proof_path.read_text("utf-8"))
        need(verified.get("files")==14 and
             verified.get("release_accepted") is False and
             verified.get("menu10_sha256")==gate.MENU_SHA and
             stage_proof.get("index_preimage_mode")=="D02_CREATIVE_WOW200_VERIFIED" and
             stage_proof.get("menu10_asset_verified") is True and
             stage_proof.get("release_accepted") is False,
             "T06_MEGAB_R76_SOURCE_AND_ASSET_ADMISSION_HOLD")
        megab_attestation={
            "status":"VERIFIED_IN_SAME_NSIS_PAYLOAD_NOT_E07",
            "asset_count":14,
            "menu10_sha256":gate.MENU_SHA,
            "index_sha256":sha(payload/"Assets/index.html"),
            "asset_receipt_sha256":sha(payload/"Assets/mega814/MEGA814_RECEIPT.json"),
            "release_accepted":False
        }
        print("T06_MEGAB_R76_SAME_ONEHOST_ASSETS_14_PASS_NOT_E07",flush=True)
    backend=payload/"Backend"
    backend.mkdir(exist_ok=True)
    shutil.copy2(exe_path,backend/exe_path.name)
    need(sha(backend/exe_path.name)==candidate_sha,
         "T06_BUNDLED_NATIVE_EXE_SHA_MISMATCH")
    inventory=[]
    for file in sorted(payload.rglob("*")):
        if file.is_dir():continue
        need(file.is_file() and not file.is_symlink(),"T06_PAYLOAD_REPARSE_HOLD")
        inventory.append({"path":file.relative_to(payload).as_posix(),
                          "bytes":file.stat().st_size,"sha256":sha(file)})
    manifest={"schema":"NOX_P01_PAYLOAD_SHA256_V1","entrypoint":"NOX.P01.Shell.exe",
        "taskId":"NOX-V16-E06-CANDIDATE","runId":"NOX-V16-T06-WINDOWS-CANDIDATE",
        "version":"16.0.0","files":inventory}
    manifest_file=payload/"payload.sha256.json"
    manifest_file.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    installer_dir=root/"Installer"
    proof=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
        "-ExecutionPolicy","Bypass","-File",
        str(installer_dir/"Verify-Payload.ps1"),"-Root",str(payload),
        "-Manifest",str(manifest_file)],capture_output=True,text=True,timeout=180)
    need(proof.returncode==0,"T06_ORIGINAL_OWNER_MANIFEST_VERIFY_HOLD:"+proof.stdout[-900:]+proof.stderr[-900:])
    nsis=shutil.which("makensis.exe") or next((str(p) for p in
       (Path("C:/Program Files (x86)/NSIS/makensis.exe"),
        Path("C:/Program Files/NSIS/makensis.exe")) if p.is_file()),None)
    if nsis is None:
        chocolatey=shutil.which("choco")
        need(chocolatey is not None,"T06_FREE_NSIS_WINDOWS_COMPILER_MISSING")
        installed=subprocess.run([chocolatey,"install","nsis","--yes",
           "--no-progress","--limit-output"],capture_output=True,text=True,timeout=400)
        need(installed.returncode==0,"T06_EPHEMERAL_NSIS_INSTALL_HOLD")
        nsis=next((str(p) for p in
           (Path("C:/Program Files (x86)/NSIS/makensis.exe"),
            Path("C:/Program Files/NSIS/makensis.exe")) if p.is_file()),None)
    need(nsis is not None,"T06_NSIS_PATH_HOLD")
    setup=staged/"NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
    args=[nsis,"/V2",
       "/DPAYLOAD_DIR="+str(payload),
       "/DVERIFY_SCRIPT="+str(installer_dir/"Verify-Payload.ps1"),
       "/DPREFLIGHT_SCRIPT="+str(installer_dir/"Preflight-InstallPath.ps1"),
       "/DREMOVE_SCRIPT="+str(installer_dir/"Remove-InstalledPayload.ps1"),
       "/DOUTPUT_SETUP="+str(setup),
       "/DAPP_VERSION=16.0.0",str(installer_dir/"NOX-HELION-Setup.nsi")]
    compiled=subprocess.run(args,capture_output=True,text=True,timeout=600)
    (staged/"NSIS_CANDIDATE_BUILD_LOG.txt").write_text(
         compiled.stdout+"\n"+compiled.stderr,encoding="utf-8")
    need(compiled.returncode==0 and setup.is_file(),
         "T06_ORIGINAL_NSIS_CANDIDATE_BUILD_HOLD")
    candidate={"schema":"NOX-E06-ONEHOST-CANDIDATE-v1",
         "source_zip_sha256":EXPECTED_ZIP_SHA,
         "wpf_sha256":sha(entry),"backend_sha256":candidate_sha,
         "manifest_sha256":sha(manifest_file),
         "setup_sha256":sha(setup),"setup_bytes":setup.stat().st_size,
         "backend_native_stdio_windows_exe_smoke":"PASS",
         "wpf_source_compilation":"PASS","wpf_installed_interactive_qa":"NOT_RUN",
         "e07":"NOT_ACCEPTED","release_accepted":False}
    if megab_attestation is not None:
        candidate["mega814"]=megab_attestation
    (staged/"ONEHOST_CANDIDATE_RECEIPT.json").write_text(
         json.dumps(candidate,indent=2),encoding="utf-8")
    print("T06_ORIGINAL_NSIS_ONEHOST_CANDIDATE_BUILT",candidate["setup_sha256"],flush=True)
    return candidate
