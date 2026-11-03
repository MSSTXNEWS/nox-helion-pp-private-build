"""NOX HELION T06 · Same-VM installed candidate smoke, NOT independent E07.

Reuse original P01 NSIS silently on an explicitly disposable CircleCI or GitHub Actions Windows runner.
No second VM, no download of artifacts or app assets, no source rewrite,
no paid service, and no changes to a pre-existing installed NOX.

The only route exercised is real model inventory over authenticated framed P02
IPC. Actual WPF GUI, Ollama chat/STOP, model downloads and E07 remain HOLD.
"""
from __future__ import annotations

import platform
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time
from t06_uninstall_admission import owned_payload_paths, verify_original_uninstall

ROOT=Path(__file__).resolve().parents[2]
ON_GITHUB=os.environ.get("GITHUB_ACTIONS")=="true"
ON_LOCAL_BRIDGE=os.environ.get("NOX_T06_LOCAL_BRIDGE")=="YES"
# The imported T06 bridge and the original diagnostic builder have different
# real output paths and incompatible receipt schemas. Never mix their proofs.
OUTPUT=ROOT/("work/t06-local-bridge" if ON_LOCAL_BRIDGE else
             "work/e06/onehost-wow-diagnostic" if ON_GITHUB else "work/e06/onehost-r66")
BUILD=ROOT/"work/t06-wpf-p02-compile" if ON_LOCAL_BRIDGE else OUTPUT
CANDIDATE=BUILD/("ONEHOST_CANDIDATE_RECEIPT.json" if ON_LOCAL_BRIDGE else "ONEHOST_DIAGNOSTIC_RECEIPT.json")
SETUP=BUILD/("NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe" if ON_LOCAL_BRIDGE else "NOX-HELION-V16-DIAGNOSTIC-SETUP.exe")
PAYLOAD=BUILD/"payload"
NATIVE_PROOF=(ROOT/"work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json" if ON_LOCAL_BRIDGE else
              ROOT/("work/candidate/NATIVE_ONEHOST_SMOKE.json" if ON_GITHUB else "work/e06/NATIVE_ONEHOST_SMOKE.json"))
BUILT_HANDOFF=BUILD/"E07_BUILT_HANDOFF.json"
NSIS_PROOF=OUTPUT/"T06_INSTALLED_SMOKE.json"

def require(condition:bool,code:str)->None:
    if not condition: raise RuntimeError(code)

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def regular(path:Path)->bool:
    return path.is_file() and not path.is_symlink() and (
        not getattr(path,"is_junction",lambda:False)())

def strict_json_object(raw: bytes, code: str, max_bytes: int = 1048576) -> dict:
    """Only unambiguous, bounded JSON objects may count as native proof."""
    require(type(raw) is bytes and 2 <= len(raw) <= max_bytes, code)
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate proof key")
            obj[key] = value
        return obj
    def finite_float(token):
        val = float(token)
        if not math.isfinite(val):
            raise ValueError("nonfinite proof number")
        return val
    def reject_constant(_token):
        raise ValueError("nonfinite JSON constant")
    try:
        decoded = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_pairs,
            parse_float=finite_float,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, TypeError, OverflowError) as exc:
        raise RuntimeError(code) from exc
    require(type(decoded) is dict, code)
    return decoded

def strict_receipt(path: Path, code: str) -> dict:
    """Bound proof input before parsing; never follow a known redirected file."""
    require(regular(path), code)
    try:
        with path.open("rb") as stream:
            payload = stream.read(4 * 1024 * 1024 + 1)
    except OSError as exc:
        raise RuntimeError(code) from exc
    return strict_json_object(payload, code, max_bytes=4 * 1024 * 1024)

def plain_parents(path:Path,base:Path)->bool:
    try:
        cursor=path
        while cursor!=base:
            # A dangling Windows junction can report exists() == False.
            # Check the reparse identity before trusting any ancestor.
            if cursor.is_symlink() or getattr(cursor,"is_junction",lambda:False)():
                return False
            parent=cursor.parent
            if parent==cursor: return False
            cursor=parent
        return (base.is_dir() and not base.is_symlink() and
                not getattr(base,"is_junction",lambda:False)())
    except (OSError,ValueError):return False

def run(args:list[str],timeout:int)->dict:
    start=time.monotonic()
    try:
        result=subprocess.run(args,capture_output=True,timeout=timeout,
                              cwd=ROOT,check=False)
        return {"code":result.returncode,
                "elapsed":round(time.monotonic()-start,2),
                "stdout_tail":result.stdout[-650:].decode("utf-8",errors="replace"),
                "stderr_tail":result.stderr[-650:].decode("utf-8",errors="replace")}
    except subprocess.TimeoutExpired:
        return {"code":124,"elapsed":round(time.monotonic()-start,2),
                "stdout_tail":"","stderr_tail":"TIMEOUT"}

def framed(binary:Path,data_dir:Path,receipt:dict)->dict:
    # The bridge's verified frozen route is models.installed. Its chat.model
    # can correctly return provider HOLD on an empty disposable CI machine.
    route="models.installed" if ON_LOCAL_BRIDGE else "chat.model"
    request={
        "protocol":"NOX-P02-NATIVE-v1",
        "requestId":"aa55bb66cc77dd88ee99ff0011223344",
        "route":route,
        "payload":{},
        "runId":"NOX-P02-INSTALLED-CANDIDATE-20261030"
    }
    raw=json.dumps(request,separators=(",",":")).encode("utf-8")
    start=time.monotonic()
    response=subprocess.run([str(binary),"--native-stdio","--run-id",request["runId"],
                             "--data-dir",str(data_dir)],input=struct.pack(">I",len(raw))+raw,
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            timeout=95,cwd=binary.parent,check=False)
    require(response.returncode==0,"T06_INSTALLED_BACKEND_PROCESS_FAILED")
    content=response.stdout
    require(len(content)>=5,"T06_INSTALLED_BACKEND_FRAME_ABSENT")
    n=struct.unpack(">I",content[:4])[0]
    require(1<=n<=1048576 and len(content)==n+4,"T06_INSTALLED_BACKEND_FRAME_BOUNDS")
    answer=strict_json_object(content[4:],"T06_INSTALLED_NATIVE_REPLY_JSON_HOLD")
    require(answer.get("protocol")==request["protocol"] and
            answer.get("runId")==request["runId"] and
            answer.get("requestId")==request["requestId"] and
            answer.get("status")=="OK" and
            type(answer.get("result")) is dict and
            type(answer["result"].get("models")) is list,
            "T06_INSTALLED_BACKEND_FRAME_IDENTITY_OR_MODEL_HOLD")
    return {"status":"PASS","route":route,
            "run_id_matched":True,"request_id_matched":True,
            "duration_seconds":round(time.monotonic()-start,2),
            "binary_sha256":sha(binary)}

def bridge_candidate_gate()->dict:
    """Admit the ORIGINAL imported T06 OneHost output, never forge E07 evidence."""
    native_source=ROOT/"work/t06-manual-source-inspect/NATIVE_STDIO_SOURCE_SMOKE.json"
    required=(CANDIDATE,SETUP,NATIVE_PROOF,native_source,
              PAYLOAD/"NOX.P01.Shell.exe",
              PAYLOAD/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe",
              PAYLOAD/"payload.sha256.json")
    require(all(regular(p) for p in required),"T06_BRIDGE_CANDIDATE_FILE_MISSING")
    source=strict_receipt(CANDIDATE,"T06_CANDIDATE_RECEIPT_JSON_HOLD")
    # Bind exactly the actual NSIS original R11 preflight source before Setup;
    # registry presence still cannot certify installed GUI or E07.
    staged_preflight=BUILD/"R11/Installer/Preflight-InstallPath.ps1"
    require(regular(staged_preflight),
            "T06_WEBVIEW2_ORIGINAL_NSIS_PREFLIGHT_NOT_STAGED")
    staged_text=staged_preflight.read_text("utf-8-sig")
    require(source.get("webview2_p01_source_git_blob")==
                "e683e30b4e6fc32c31652061c569d6ce77c2cb2e" and
            re.fullmatch("[0-9a-f]{64}",str(source.get("webview2_p01_preflight_sha256",""))) and
            source["webview2_p01_preflight_sha256"]==sha(staged_preflight) and
            "[Microsoft.Win32.RegistryView]::Registry32" in staged_text and
            "[Microsoft.Win32.RegistryView]::Registry64" in staged_text and
            "P01_WEBVIEW2_RUNTIME_MISSING" in staged_text,
            "T06_ORIGINAL_NSIS_WEBVIEW2_PREFLIGHT_SOURCELOCK_HOLD")
    native=strict_receipt(NATIVE_PROOF,"T06_NATIVE_RECEIPT_JSON_HOLD")
    original=strict_receipt(native_source,"T06_ORIGINAL_SOURCE_RECEIPT_JSON_HOLD")
    source_zip="90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"
    original_zip="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
    wpf=PAYLOAD/"NOX.P01.Shell.exe"
    backend=PAYLOAD/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"
    manifest=PAYLOAD/"payload.sha256.json"
    require(source.get("schema")=="NOX-E06-ONEHOST-CANDIDATE-v1" and
            source.get("source_zip_sha256")==source_zip and
            source.get("release_accepted") is False and
            source.get("e07")=="NOT_ACCEPTED" and
            source.get("wpf_source_compilation")=="PASS" and
            source.get("backend_native_stdio_windows_exe_smoke")=="PASS" and
            type(source.get("setup_bytes")) is int and
            source["setup_bytes"]==SETUP.stat().st_size and
            re.fullmatch("[0-9a-f]{64}",str(source.get("setup_sha256",""))) and
            sha(SETUP)==source["setup_sha256"],
            "T06_BRIDGE_SETUP_SOURCE_IDENTITY_HOLD")
    require(native.get("phase")=="BUILT_AND_NATIVE_STDIO_SMOKE_PASS" and
            native.get("native_windows_exe_request_reply")=="PASS" and
            native.get("native_modelcenter_installed_read_only")=="PASS" and
            native.get("models_installed_uses_original_local_discovery") is True and
            native.get("original_729_unchanged") is True and
            native.get("source_original_archive_sha256")==original_zip and
            native.get("installed_wpf_e07") is False and
            native.get("release_accepted") is False and
            native.get("exe_file")==backend.name and
            type(native.get("exe_size")) is int and
            native["exe_size"]==backend.stat().st_size and
            native.get("exe_sha256")==source.get("backend_sha256") and
            sha(backend)==source["backend_sha256"],
            "T06_BRIDGE_NATIVE_SOURCE_SHA_HOLD")
    require(original.get("phase")=="ORIGINAL_PYTHON_SOURCE_EXECUTION_WINDOWS" and
            original.get("source_zip_sha256")==original_zip and
            original.get("original_archive_unchanged") is True and
            original.get("run_id_matched") is True and
            original.get("request_id_matched") is True and
            original.get("native_process_exit_code")==0 and
            original.get("release_accepted") is False and
            sha(wpf)==source.get("wpf_sha256") and
            sha(manifest)==source.get("manifest_sha256"),
            "T06_BRIDGE_SOURCE_OR_WPF_SHA_HOLD")
    inventory=strict_receipt(manifest,"T06_PAYLOAD_MANIFEST_JSON_HOLD")
    require(inventory.get("schema")=="NOX_P01_PAYLOAD_SHA256_V1" and
            inventory.get("entrypoint")=="NOX.P01.Shell.exe" and
            type(inventory.get("files")) is list and
            len(inventory["files"])>=12,"T06_BRIDGE_PAYLOAD_MANIFEST_HOLD")
    seen=set()
    for item in inventory["files"]:
        require(type(item) is dict,"T06_BRIDGE_MANIFEST_ENTRY_INVALID")
        name=item.get("path")
        require(type(name) is str and name and "\\" not in name and
                "\x00" not in name and ":" not in name and
                all(part not in ("",".","..") for part in name.split("/")) and
                name.casefold() not in seen,"T06_BRIDGE_PAYLOAD_PATH_INVALID")
        seen.add(name.casefold())
        path=PAYLOAD.joinpath(*name.split("/"))
        require(regular(path) and
                path.resolve(strict=True).is_relative_to(PAYLOAD.resolve(strict=True)) and
                item.get("bytes")==path.stat().st_size and
                item.get("sha256")==sha(path),
                "T06_BRIDGE_PAYLOAD_FILE_SHA_HOLD")
    require("NOX.P01.Shell.exe".casefold() in seen and
            "Backend/NOX_HELION_PRIVATE_CANDIDATE.exe".casefold() in seen,
            "T06_BRIDGE_PAYLOAD_BINARY_UNLISTED")
    return {"setup_sha256":source["setup_sha256"],
            "wpf_sha256":source["wpf_sha256"],
            "backend_sha256":source["backend_sha256"],
            "manifest_sha256":source["manifest_sha256"],
            "native_source_receipt":"ORIGINAL_FROZEN_MODELCENTER_PASS_NOT_E07",
            "manifest_files_checked":len(seen)}

def candidate_gate()->dict:
    if ON_LOCAL_BRIDGE:
        return bridge_candidate_gate()
    require(all(regular(x) for x in (CANDIDATE,SETUP,NATIVE_PROOF,BUILT_HANDOFF)),
            "T06_CANDIDATE_EVIDENCE_MISSING")
    source=strict_receipt(CANDIDATE,"T06_CANDIDATE_RECEIPT_JSON_HOLD")
    native=strict_receipt(NATIVE_PROOF,"T06_NATIVE_RECEIPT_JSON_HOLD")
    handoff=strict_receipt(BUILT_HANDOFF,"T06_BUILT_HANDOFF_JSON_HOLD")
    require(source.get("schema")=="NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1" and
            source.get("release_accepted") is False and source.get("one_visible_host") is True and
            source.get("status")=="WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED" and
            type(source.get("installer_bytes")) is int and
            source["installer_bytes"]==SETUP.stat().st_size and
            re.fullmatch("[0-9a-f]{64}",str(source.get("installer_sha256",""))) and
            sha(SETUP)==source["installer_sha256"],
            "T06_INSTALLER_IDENTITY_SHA_HOLD")
    require(native.get("schema")=="NOX_NATIVE_ONEHOST_SMOKE_V2" and
            native.get("phase") in ("BUILT_AND_NATIVE_STDIO_SMOKE_PASS","BUILT_AND_NATIVE_STDIO_SMOKE_HOLD") and
            native.get("offline_backbone_status")=="PASS" and
            native.get("transport_status")=="PASS" and
            native.get("original_729_unchanged") is True and
            native.get("release_accepted") is False and
            native.get("exe_sha256")==source.get("python_backend_sha256") and
            ((native.get("live_model_status")=="HOLD" and native.get("native_windows_exe_request_reply")=="HOLD") or
             (native.get("live_model_status")=="PASS" and native.get("native_windows_exe_request_reply")=="PASS")),
            "T06_NATIVE_OFFLINE_BACKBONE_IDENTITY_HOLD")
    require(handoff.get("schema")=="NOX_V16_E07_IMMUTABLE_HANDOFF_V1" and
            handoff.get("phase")=="BUILT" and handoff.get("release_accepted") is False and
            handoff.get("independent_e07_cases_accepted")==0 and
            handoff.get("source_receipts_729_parity_verified") is True and
            handoff.get("setup_sha256")==source["installer_sha256"] and
            handoff.get("published_exe_sha256")==source.get("wpf_exe_sha256") and
            handoff.get("source_commit_sha1")==native.get("source_commit") and
            handoff.get("installed_exe_sha256") is None and
            handoff.get("original_zip_sha256")=="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a",
            "T06_E07_BUILT_HANDOFF_IDENTITY_HOLD")
    wpf=PAYLOAD/"NOX.P01.Shell.exe"
    py=PAYLOAD/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"
    manifest=PAYLOAD/"payload.sha256.json"
    require(all(regular(x) for x in (wpf,py,manifest)) and
            sha(wpf)==source.get("wpf_exe_sha256") and
            sha(py)==source.get("python_backend_sha256") and
            sha(manifest)==source.get("payload_manifest_sha256"),
            "T06_PAYLOAD_ORIGINAL_WPF_NATIVE_SHA_HOLD")
    inventory=strict_receipt(manifest,"T06_PAYLOAD_MANIFEST_JSON_HOLD")
    require(inventory.get("schema")=="NOX_P01_PAYLOAD_SHA256_V1" and
            inventory.get("entrypoint")=="NOX.P01.Shell.exe" and
            type(inventory.get("files")) is list and len(inventory["files"])>=12,
            "T06_ORIGINAL_NSIS_MANIFEST_SCHEMA_HOLD")
    seen=set()
    for item in inventory["files"]:
        name=item.get("path")
        require(type(name) is str and name and "\\" not in name and "\x00" not in name,
                "T06_PAYLOAD_FILE_PATH_INVALID")
        parts=Path(name).parts
        require(not Path(name).is_absolute() and not any(p in (".","..") for p in parts) and
                name.casefold() not in seen,"T06_PAYLOAD_PATH_ESCAPE_OR_DUPLICATE")
        seen.add(name.casefold())
        file=PAYLOAD.joinpath(*parts)
        require(regular(file) and file.resolve(strict=True).is_relative_to(PAYLOAD.resolve(strict=True)) and
                item.get("sha256")==sha(file) and item.get("bytes")==file.stat().st_size,
                "T06_PAYLOAD_MANIFEST_FILE_HASH_HOLD")
    return {"setup_sha256":source["installer_sha256"],"wpf_sha256":source["wpf_exe_sha256"],
            "backend_sha256":source["python_backend_sha256"],
            "manifest_sha256":source["payload_manifest_sha256"],
            "build_id":handoff["build_id"],
            "native_source_receipt":"OFFLINE_BACKBONE_PASS_LIVE_MODEL_"+native["live_model_status"],
            "manifest_files_checked":len(seen)}

def gitlab_native_windows_amd64(reported_arch, platform_name, host_machine, pointer_bits):
    """Check genuine Windows x64 even if GitLab omits optional runner arch export.

    Explicit mismatches deny; absent env cannot bypass actual platform, bitness
    and CPU architecture. Other original project/job/consent controls remain.
    """
    if (type(reported_arch) is not str or type(platform_name) is not str or
            type(host_machine) is not str or type(pointer_bits) is not int):
        return False
    return (platform_name == 'win32' and pointer_bits == 64 and
            host_machine.strip().lower() in ('amd64', 'x86_64') and
            reported_arch.strip().lower() in ('', 'windows/amd64'))


WEBVIEW2_POSTINSTALL_POLL_SECONDS = (0, 2, 4, 8, 12, 18, 24, 30)


def valid_webview2_registration(registration: dict) -> bool:
    """Fail-closed diagnostic, never a substitute for original P01 preflight."""
    if type(registration) is not dict:
        return False
    views = ("HKLM_32_VIEW", "HKLM_64_VIEW", "HKCU_32_VIEW", "HKCU_64_VIEW", "HKCU_USER")
    for view in views:
        row = registration.get(view)
        if type(row) is not dict or row.get("present") is not True:
            continue
        pv = row.get("pv")
        if type(pv) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", pv):
            if int(pv.split(".", 1)[0]) > 0:
                return True
    return False


def webview2_registry_access_denied(registration: dict) -> bool:
    """Do not mistake EdgeUpdate registry access denial for an absent Runtime."""
    return type(registration) is dict and any(
        type(row) is dict and row.get("access_denied") is True
        for row in registration.values()
    )


def webview2_registry_probe_failed(registration: dict) -> bool:
    """Unknown EdgeUpdate registry faults cannot authorize retrying installation."""
    if type(registration) is not dict:
        return True
    for row in registration.values():
        if type(row) is not dict or row.get("probe_error") is True:
            return True
        if (row.get("present") is False and row.get("access_denied") is not True
                and row.get("winerror") not in (None, 2, 3)):
            return True
    return False


def poll_webview2_postinstall(run_preflight, probe_registration, pause,
                              delays=WEBVIEW2_POSTINSTALL_POLL_SECONDS):
    """Wait for EdgeUpdate asynchronous registration; P01 owner preflight alone grants PASS."""
    attempts = []
    last = None
    registry = {}
    for delay in delays:
        if delay:
            pause(delay)
        last = run_preflight()
        reason = last["stdout_tail"] + "\n" + last["stderr_tail"]
        state = ("PASS" if last["code"] == 0 else
                 "RUNTIME_MISSING" if "P01_WEBVIEW2_RUNTIME_MISSING" in reason else
                 "UNRELATED_HOLD")
        attempts.append({"delay_seconds": delay,
                         "exit_code": last["code"],
                         "strict_preflight_status": state})
        if state == "PASS":
            return last, attempts, probe_registration(), "PASS_BY_ORIGINAL_PREFLIGHT"
        if state == "UNRELATED_HOLD":
            return last, attempts, probe_registration(), "UNRELATED_HOLD"
        registry = probe_registration()
        if webview2_registry_access_denied(registry):
            return last, attempts, registry, "REGISTRY_ACCESS_DENIED"
        if webview2_registry_probe_failed(registry):
            return last, attempts, registry, "REGISTRY_PROBE_FAILED"
        if valid_webview2_registration(registry):
            return last, attempts, registry, "REGISTRY_PREFLIGHT_DIVERGENCE"
    return last, attempts, registry, "RUNTIME_MISSING"


def webview2_registration_diagnostic()->dict:
    """Read-only, non-authoritative registry evidence on the SAME Windows CI VM.

    The original owner Preflight-InstallPath.ps1 alone decides PASS. This
    probe distinguishes installed runtime vs a stale/incorrect registry view,
    without adding new install attempts or accepting Microsoft Edge Stable.
    """
    import winreg
    guid="{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    suffix="Microsoft\\EdgeUpdate\\Clients\\"+guid
    targets=(
        ("HKLM_32_VIEW",winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\\"+suffix,winreg.KEY_WOW64_32KEY),
        ("HKLM_64_VIEW",winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\\"+suffix,winreg.KEY_WOW64_64KEY),
        ("HKCU_32_VIEW",winreg.HKEY_CURRENT_USER,"Software\\"+suffix,winreg.KEY_WOW64_32KEY),
        ("HKCU_64_VIEW",winreg.HKEY_CURRENT_USER,"Software\\"+suffix,winreg.KEY_WOW64_64KEY),
        ("HKCU_USER",winreg.HKEY_CURRENT_USER,"Software\\"+suffix,0),
    )
    result={}
    for label,root,path,view in targets:
        try:
            with winreg.OpenKey(root,path,0,winreg.KEY_READ|view) as handle:
                value,value_type=winreg.QueryValueEx(handle,"pv")
            result[label]={"present":True,
                           "pv":str(value)[:64] if value_type==winreg.REG_SZ else "",
                           "value_type":value_type}
        except OSError as exc:
            # WinError 5 is not equivalent to ERROR_FILE_NOT_FOUND. Prevent
            # blind CI re-provisioning when the EdgeUpdate view is unreadable.
            winerror=getattr(exc,"winerror",None)
            denied=(isinstance(exc, PermissionError) or winerror==5)
            missing=(isinstance(exc, FileNotFoundError) or winerror in (2, 3))
            result[label]={"present":False,"winerror":winerror,
                           "access_denied":denied,
                           "probe_error":not (denied or missing)}
    return result

def ensure_official_webview2_on_ci(preflight:dict,script:Path,install:Path,
                                   report:dict)->dict:
    """Only an opt-in disposable Windows CI host can provision official WebView2.

    Preserve strict valid Microsoft Authenticode; on a failed online bootstrapper
    signature, try the DIFFERENT official x64 Evergreen standalone installer.
    Never execute either unsigned payload and never provision on customer systems.
    """
    if preflight["code"] == 0:
        return preflight
    reason=preflight["stdout_tail"]+"\n"+preflight["stderr_tail"]
    require("P01_WEBVIEW2_RUNTIME_MISSING" in reason,
            "T06_PREFLIGHT_FAILED_FOR_UNRELATED_SECURITY_CAUSE")
    require(os.environ.get("NOX_M1_CI_INSTALL_WEBVIEW2")=="YES",
            "T06_OFFICIAL_WEBVIEW2_RUNTIME_REQUIRED_CI_OPT_IN")
    initial_registration=webview2_registration_diagnostic()
    report["installer_lifecycle"]["webview2_initial_registration"]=initial_registration
    require(not webview2_registry_access_denied(initial_registration),
            "T06_WEBVIEW2_REGISTRY_ACCESS_DENIED")
    require(not webview2_registry_probe_failed(initial_registration),
            "T06_WEBVIEW2_REGISTRY_PROBE_FAILED")
    # Never install another signed Runtime when it already has real pv and the
    # original P01 stage merely probes the wrong registry view.
    require(not valid_webview2_registration(initial_registration),
            "T06_WEBVIEW2_STAGED_PREFLIGHT_REGISTRY_DIVERGENCE")
    from urllib.request import urlopen
    from urllib.parse import urlsplit

    ps=r"""$ErrorActionPreference='Stop'
$p=$env:NOX_WEBVIEW2_SIGNED_INSTALLER_PATH
if ([string]::IsNullOrWhiteSpace($p) -or -not (Test-Path -LiteralPath $p -PathType Leaf)) {exit 8}
$moduleManifest=Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1'
try {
  if (-not (Test-Path -LiteralPath $moduleManifest -PathType Leaf)) { throw 'SECURITY_MODULE_MANIFEST_MISSING' }
  Import-Module -Name $moduleManifest -ErrorAction Stop
  $signatureCmd=Get-Command -Name 'Get-AuthenticodeSignature' -CommandType Cmdlet -ErrorAction Stop
} catch {
  [Console]::Error.WriteLine("T06_AUTHENTICODE_MODULE_UNAVAILABLE ps=$($PSVersionTable.PSVersion) module=$moduleManifest error=$($_.Exception.Message)")
  exit 9
}
try {
  $s=& $signatureCmd -LiteralPath $p -ErrorAction Stop
} catch {
  [Console]::Error.WriteLine("T06_AUTHENTICODE_EXECUTION_UNAVAILABLE error=$($_.Exception.Message)")
  exit 9
}
$subject=if ($null -ne $s.SignerCertificate) {[string]$s.SignerCertificate.Subject} else {''}
@{status=[string]$s.Status;subject=$subject;message=[string]$s.StatusMessage} |
  ConvertTo-Json -Compress
$publisherOk = $subject -cmatch '\ACN=Microsoft Corporation,\s*O=Microsoft Corporation(?:,|\z)'
if ($s.Status -ne 'Valid' -or -not $publisherOk) {exit 7}
exit 0"""

    def verify_official_installer(target:Path,kind:str)->bool:
        env=dict(os.environ)
        env["NOX_WEBVIEW2_SIGNED_INSTALLER_PATH"]=str(target)
        check=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
              "-Command",ps],env=env,capture_output=True,timeout=50,check=False)
        evidence={"kind":kind,"signature_exit":check.returncode,
                  "download_sha256":sha(target),
                  "bytes":target.stat().st_size,
                  "authenticode":check.stdout[-1200:].decode("utf-8",errors="replace").strip(),
                  "diagnostic_error":check.stderr[-300:].decode("utf-8",errors="replace").strip()}
        report["installer_lifecycle"].setdefault("webview2_signature_attempts",[]).append(evidence)
        print("T06_WEBVIEW2_AUTHENTICODE "+json.dumps(evidence,sort_keys=True),flush=True)
        if check.returncode==9:
            require(False,"T06_WEBVIEW2_AUTHENTICODE_VERIFIER_UNAVAILABLE")
        return check.returncode==0

    def download_microsoft(url:str,name:str,min_bytes:int,max_bytes:int)->Path:
        target=OUTPUT/name
        require(not target.exists() and not target.is_symlink(),
                "T06_WEBVIEW2_DOWNLOAD_COLLISION")
        with urlopen(url,timeout=90) as response:
            final=urlsplit(response.geturl())
            host=(final.hostname or "").lower()
            require(final.scheme=="https" and
                    (host=="microsoft.com" or host.endswith(".microsoft.com")),
                    "T06_WEBVIEW2_UNTRUSTED_DOWNLOAD_REDIRECT")
            size=0
            with target.open("xb") as dest:
                while chunk:=response.read(65536):
                    size+=len(chunk)
                    require(size<=max_bytes,"T06_WEBVIEW2_INSTALLER_OVERSIZE")
                    dest.write(chunk)
                dest.flush()
                os.fsync(dest.fileno())
        with target.open("rb") as stream:
            magic=stream.read(2)
        require(min_bytes<=size<=max_bytes and magic==b"MZ",
                "T06_WEBVIEW2_OFFICIAL_INSTALLER_INVALID")
        return target

    def strict_postinstall_preflight(label:str)->dict:
        """Wait for async Microsoft EdgeUpdate registration, not for browser Edge.

        The ORIGINAL signed WebView2 owner preflight exclusively decides PASS.
        Registry mismatch is an explicit HOLD, never a substitute PASS.
        """
        def owner_preflight():
            return run(["powershell.exe","-NoProfile","-NonInteractive",
                        "-ExecutionPolicy","Bypass","-File",str(script),
                        "-InstallRoot",str(install)],80)
        result, attempts, registration, verdict = poll_webview2_postinstall(
            owner_preflight, webview2_registration_diagnostic, time.sleep)
        report["installer_lifecycle"]["webview2_"+label+"_strict_preflight_poll"]=attempts
        report["installer_lifecycle"]["webview2_"+label+"_registration_diagnostic"]=registration
        report["installer_lifecycle"]["webview2_"+label+"_strict_preflight_verdict"]=verdict
        print("T06_WEBVIEW2_REGISTRATION_DIAGNOSTIC "+json.dumps(
            {"kind":label,"registry":registration,"strict_result":result["code"],
             "verdict":verdict},sort_keys=True),flush=True)
        require(verdict!="REGISTRY_ACCESS_DENIED",
                "T06_WEBVIEW2_REGISTRY_ACCESS_DENIED")
        require(verdict!="REGISTRY_PROBE_FAILED",
                "T06_WEBVIEW2_REGISTRY_PROBE_FAILED")
        require(verdict!="REGISTRY_PREFLIGHT_DIVERGENCE",
                "T06_WEBVIEW2_STAGED_PREFLIGHT_REGISTRY_DIVERGENCE")
        return result

    target=download_microsoft("https://go.microsoft.com/fwlink/p/?LinkId=2124703",
                              "MicrosoftEdgeWebview2Setup.exe",100000,15000000)
    kind="evergreen-bootstrapper"
    if not verify_official_installer(target,kind):
        # Official alternative, not a bypass: it must independently chain to a
        # valid Microsoft signer. Never run the failed bootstrapper.
        target=download_microsoft("https://go.microsoft.com/fwlink/?linkid=2124701",
                        "MicrosoftEdgeWebView2RuntimeInstallerX64.exe",20000000,350000000)
        kind="evergreen-standalone-x64"
        require(verify_official_installer(target,kind),
                "T06_WEBVIEW2_MICROSOFT_SIGNATURE_HOLD")
    report["installer_lifecycle"]["webview2_selected_verified_source"]=kind
    provision=run([str(target),"/silent","/install"],290)
    report["installer_lifecycle"]["microsoft_webview2_provision_ci"]={
        "exit_code":provision["code"],"signed_microsoft":True,"kind":kind}
    require(provision["code"]==0,"T06_WEBVIEW2_RUNTIME_PROVISION_FAILED")
    fresh=strict_postinstall_preflight(kind)
    report["installer_lifecycle"]["webview2_first_postinstall_preflight"]=fresh
    if fresh["code"]!=0:
        reason=fresh["stdout_tail"]+"\n"+fresh["stderr_tail"]
        require("P01_WEBVIEW2_RUNTIME_MISSING" in reason,
                "T06_WEBVIEW2_POSTINSTALL_UNRELATED_PREFLIGHT_HOLD")
        if kind=="evergreen-bootstrapper":
            # Signed bootstrapper can exit successfully before runtime is usable.
            # Retry only with the *different* official x64 standalone, also
            # verifying its Authenticode chain and Microsoft Corporation signer.
            target=download_microsoft(
                "https://go.microsoft.com/fwlink/?linkid=2124701",
                "MicrosoftEdgeWebView2RuntimeInstallerX64.exe",20000000,350000000)
            require(verify_official_installer(target,"evergreen-standalone-x64"),
                    "T06_WEBVIEW2_MICROSOFT_SIGNATURE_HOLD")
            fallback=run([str(target),"/silent","/install"],290)
            report["installer_lifecycle"]["webview2_standalone_fallback"]={
                "exit_code":fallback["code"],"signed_microsoft":True,
                "kind":"evergreen-standalone-x64"}
            require(fallback["code"]==0,
                    "T06_WEBVIEW2_STANDALONE_RUNTIME_PROVISION_FAILED")
            fresh=strict_postinstall_preflight("evergreen-standalone-x64")
    report["installer_lifecycle"]["webview2_final_postinstall_preflight"]=fresh
    require(fresh["code"]==0,"T06_WEBVIEW2_RUNTIME_STILL_MISSING_AFTER_INSTALL")
    return fresh

def wpf_startup_marker_flags(window: str) -> dict:
    """Only bracket-prefixed original shell.log events; no text-substring success."""
    events=("INIT_BEGIN","NAV_START","NAV_OK","NAV_FAIL","BLOCK_NAV",
            "WEBVIEW_PROCESS_FAILED","P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK",
            "INIT_ERROR","P02_ORIGINAL_NATIVE_HOLD")
    lines=window.splitlines()
    out={name:False for name in events}
    for line in lines:
        if not line.startswith("["):
            continue
        prefix,sep,msg=line.partition("] ")
        if not sep or not 2<=len(prefix)<=160:
            continue
        name=msg.split(" ",1)[0].rstrip("\r")
        if name in out: out[name]=True
    return out


def summarize_fresh_webview_navigation(window: str) -> dict:
    """Bounded diagnostics from newly read WPF log bytes; never include raw URLs.

    Does not grant GUI readiness, native capabilities, or release acceptance.
    Caller must enforce original PID/log identity + HWND evidence separately.
    """
    if type(window) is not str:
        raise TypeError("WPF_NAV_WINDOW_REQUIRED")
    failures = re.findall(r"(?m)^\[[^\]\r\n]{1,159}\] NAV_FAIL[ \t]+([A-Za-z][A-Za-z0-9]{0,63})(?=[ \t\r\n]|$)", window)
    process_failures = re.findall(
        r"(?m)^\[[^\]\r\n]{1,159}\] WEBVIEW_PROCESS_FAILED[ \t]+([A-Za-z][A-Za-z0-9]{0,63})(?=[ \t\r\n]|$)", window)
    flags=wpf_startup_marker_flags(window)
    return {
        "init_started": flags["INIT_BEGIN"],
        "nav_started": flags["NAV_START"],
        "nav_failed": flags["NAV_FAIL"],
        "nav_failure_status": failures[-1] if failures else None,
        "webview_process_failed": flags["WEBVIEW_PROCESS_FAILED"],
        "webview_process_failure_kind": process_failures[-1] if process_failures else None,
        "navigation_blocked": flags["BLOCK_NAV"],
    }


def wpf_startup_fatal_seen(seen: dict) -> bool:
    """A failed same-PID WebView2 launch cannot be certified by earlier NAV_OK.

    Treat blocking navigation, navigation errors and any WebView2 process
    failure as terminal for THIS smoke process, even after IPC succeeds.
    A new, separate installed launch must produce fresh log+HWND evidence.
    """
    return any(seen.get(event, False) is True for event in (
        "NAV_FAIL", "BLOCK_NAV", "WEBVIEW_PROCESS_FAILED",
        "INIT_ERROR", "P02_ORIGINAL_NATIVE_HOLD",
    ))


WPF_GUI_STABLE_READY_SECONDS = 8.0


def wpf_gui_stability_step(first_ready_at: float | None, now: float, *, ready: bool):
    """An early NAV_OK+IPC+HWND is not stable proof of WebView2 survival."""
    if (ready is not True or not math.isfinite(now) or
            (first_ready_at is not None and
             (not math.isfinite(first_ready_at) or now < first_ready_at))):
        return None, False
    if first_ready_at is None:
        return now, False
    return first_ready_at, now-first_ready_at>=WPF_GUI_STABLE_READY_SECONDS


def live_original_wpf_probe(exe:Path,local:Path)->dict:
    """Attest live WPF GUI/IPC from NEW bytes of the original shell log.

    The same-VM smoke is NOT independent E07. Never accept stale log
    text, a retired WPF process, a replaced log file, or native hold.
    """
    from t06_windows_hwnd_witness import find_visible_wpf_hwnd
    log=local/"NOX_HELION/P01/logs/shell.log"
    original=log.stat() if log.is_file() else None
    offset=original.st_size if original else 0
    identity=(original.st_dev,original.st_ino) if original else None
    seen={mark:False for mark in (
        "INIT_BEGIN","NAV_START","NAV_OK","NAV_FAIL","BLOCK_NAV",
        "WEBVIEW_PROCESS_FAILED","P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK",
        "INIT_ERROR","P02_ORIGINAL_NATIVE_HOLD")}
    boundary=""
    navigation={"init_started":False,"nav_started":False,"nav_failed":False,
                "nav_failure_status":None,"webview_process_failed":False,
                "webview_process_failure_kind":None,"navigation_blocked":False}
    process=None
    alive_at_proof=False
    hwnd_at_proof=None
    log_replaced=False
    stable_since=None
    stable_window_pass=False
    try:
        process=subprocess.Popen([str(exe)],cwd=exe.parent,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            if process.poll() is not None:
                break
            if log.is_file():
                current=log.stat()
                current_identity=(current.st_dev,current.st_ino)
                if identity is None:
                    identity=current_identity
                if current_identity!=identity or current.st_size<offset:
                    log_replaced=True
                    break
                if current.st_size>offset:
                    with log.open("rb") as stream:
                        stream.seek(offset)
                        chunk=stream.read(min(65536,current.st_size-offset))
                    offset+=len(chunk)
                    window=boundary+chunk.decode("utf-8",errors="replace")
                    complete_lines,separator,tail=window.rpartition("\n")
                    if separator:
                        # Never admit partial lines or marker words inside errors.
                        exact=wpf_startup_marker_flags(complete_lines)
                        for marker in seen:
                            seen[marker]=seen[marker] or exact[marker]
                        fresh=summarize_fresh_webview_navigation(complete_lines)
                        for label in ("init_started","nav_started","nav_failed",
                                      "webview_process_failed","navigation_blocked"):
                            navigation[label]=navigation[label] or fresh[label]
                        for label in ("nav_failure_status","webview_process_failure_kind"):
                            if fresh[label] is not None:
                                navigation[label]=fresh[label]
                        boundary=tail[-4096:]
                    else:
                        boundary=window[-4096:]
            if wpf_startup_fatal_seen(seen):
                break
            ready_now=False
            if seen["NAV_OK"] and seen["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"]:
                # Drain every newly appended real shell.log line before counting
                # a live-PID, visible-HWND stability interval. A browser crash
                # after NAV_OK must never become a false GUI/IPC PASS.
                latest=log.stat() if log.is_file() else None
                if (latest is None or identity is None or
                    (latest.st_dev,latest.st_ino)!=identity or
                    latest.st_size<offset):
                    log_replaced=True
                    break
                if offset==latest.st_size and process.poll() is None:
                    # Only the ORIGINAL WPF PID and a visible owned HWND count.
                    hwnd_at_proof=find_visible_wpf_hwnd(process.pid)
                    ready_now=hwnd_at_proof is not None and process.poll() is None
            stable_since,stable_window_pass=wpf_gui_stability_step(
                stable_since,time.monotonic(),ready=ready_now)
            if stable_window_pass:
                alive_at_proof=process.poll() is None
                if alive_at_proof:break
            time.sleep(0.7)
        accepted=(process.pid>0 and alive_at_proof and stable_window_pass and
                  hwnd_at_proof is not None and not log_replaced and
                  not wpf_startup_fatal_seen(seen))
        return {"pid_started":process.pid>0,
                "new_nav_ok":accepted and seen["NAV_OK"],
                "new_python_ipc_handshake":accepted and seen["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"],
                "init_error":seen["INIT_ERROR"],
                "native_hold":seen["P02_ORIGINAL_NATIVE_HOLD"],
                "live_process_at_receipt":alive_at_proof,
                "stable_ready_window_pass":accepted and stable_window_pass,
                "stable_ready_window_seconds":WPF_GUI_STABLE_READY_SECONDS,
                "real_wpf_visible_pid_hwnd":accepted,
                "real_wpf_hwnd":hex(hwnd_at_proof) if accepted else None,
                "real_wpf_hwnd_pid":process.pid if accepted else None,
                "log_replaced":log_replaced,
                "new_log_bytes_scanned":offset-(original.st_size if original else 0),
                "navigation_diagnostic":navigation,
                "wpf_shell_exact_event_flags":{name:seen[name] for name in (
                    "INIT_BEGIN","NAV_START","NAV_OK","NAV_FAIL",
                    "BLOCK_NAV","WEBVIEW_PROCESS_FAILED","INIT_ERROR")},
                "proof":"CURRENT_WINDOWS_PROCESS_NEW_SHELL_LOG",
                "independent_visual_e07":"NOT_RUN"}
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        subprocess.run(["taskkill.exe","/PID",str(process.pid),
                                        "/T","/F"],capture_output=True,timeout=20)
            finally:
                try:process.wait(timeout=8)
                except (subprocess.TimeoutExpired,OSError):pass


def main()->int:
    started=time.monotonic()
    report={"schema":"NOX-T06-INSTALLED-SMOKE-v1","phase":"HOLD",
            "environment":("GITLAB_WINDOWS_EPHEMERAL_ONLY" if ON_LOCAL_BRIDGE else
                           "GITHUB_WINDOWS_EPHEMERAL_ONLY" if ON_GITHUB else
                           "CIRCLECI_WINDOWS_EPHEMERAL_ONLY"),
            "setup_sha256":None,"installed_wpf_sha256":None,
            "installed_backend_sha256":None,
            "installed_process_gui_webview2":"NOT_TESTED",
            "chat_stream_stop_rag":"NOT_TESTED",
            "e07_independent_acceptance":"NOT_RUN",
            "release_accepted":False,"installer_lifecycle":{}}
    code=1
    try:
        circle_ci=(not ON_LOCAL_BRIDGE and os.environ.get("CIRCLECI")=="true" and
                   bool(os.environ.get("CIRCLE_BUILD_NUM")))
        github_ci=(not ON_LOCAL_BRIDGE and ON_GITHUB and
                   os.environ.get("RUNNER_OS")=="Windows" and
                   bool(os.environ.get("GITHUB_RUN_ID")) and
                   os.environ.get("NOX_E07_CI_WINDOWS_DISPOSABLE")=="YES")
        # R78 is the genuine GitLab same-VM candidate, NOT the GitHub E06
        # diagnostic candidate. Enforce project, hosted Windows runner, explicit
        # bridge mode and numeric CI job ID before any installer may execute.
        gitlab_id=os.environ.get("CI_JOB_ID","")
        gitlab_ci=(ON_LOCAL_BRIDGE and
                   os.environ.get("GITLAB_CI")=="true" and
                   os.environ.get("CI_SERVER_HOST")=="gitlab.com" and
                   os.environ.get("CI_PROJECT_PATH")=="s-grouptwet/nox-helion-pp-private-build" and
                   gitlab_native_windows_amd64(
                       os.environ.get("CI_RUNNER_EXECUTABLE_ARCH",""), sys.platform,
                       platform.machine(), struct.calcsize("P") * 8) and
                   gitlab_id.isascii() and gitlab_id.isdecimal() and
                   1 <= len(gitlab_id) <= 20)
        require(sys.platform=="win32" and (circle_ci or github_ci or gitlab_ci),
                "T06_INSTALL_SMOKE_REQUIRES_AUTHORIZED_DISPOSABLE_WINDOWS")
        ci_run_id=(gitlab_id if gitlab_ci else
                   os.environ["CIRCLE_BUILD_NUM"] if circle_ci else
                   os.environ["GITHUB_RUN_ID"])
        evidence=candidate_gate()
        report.update(evidence)
        local=os.getenv("LOCALAPPDATA","")
        local_base=Path(Path(local).anchor)
        require(local and Path(local).is_dir() and
                plain_parents(Path(local),local_base),
                "T06_WINDOWS_LOCALAPPDATA_UNTRUSTED")
        install=Path(local)/"Programs"/"NOX HELION"
        relatives=(install,Path(str(install)+".__p01_stage"),
                   Path(str(install)+".__p01_previous"),
                   Path(str(install)+".__p01_rollback_saved"))
        require(all(not p.exists() and not p.is_symlink() and
                    not getattr(p,"is_junction",lambda:False)() for p in relatives),
                "T06_CI_USER_HAS_EXISTING_NOX_INSTALL_SKIP")
        require(all(plain_parents(p,local_base) for p in relatives),
                "T06_CI_INSTALL_REPARSE_ANCESTOR_HOLD")
        origin=(ROOT/"work/t06-wpf-p02-compile/R11/Installer" if ON_LOCAL_BRIDGE else
                ROOT/"work/e06/staged/R11/Installer")
        preflight=origin/"Preflight-InstallPath.ps1"
        verify=origin/"Verify-Payload.ps1"
        require(all(regular(p) for p in (preflight,verify)),
                "T06_ORIGINAL_INSTALLER_OWNER_SCRIPTS_MISSING")
        prep=run(["powershell.exe","-NoProfile","-NonInteractive",
                  "-ExecutionPolicy","Bypass","-File",str(preflight),
                  "-InstallRoot",str(install)],70)
        report["installer_lifecycle"]["preflight_original"]=prep
        prep=ensure_official_webview2_on_ci(prep,preflight,install,report)
        report["installer_lifecycle"]["preflight_final"]=prep
        # Recheck immediately before launching the privileged-to-install
        # Setup: no preflight or EdgeUpdate side effect may redirect the root.
        require(all(plain_parents(p,local_base) and not p.exists() and
                    not p.is_symlink() and
                    not getattr(p,"is_junction",lambda:False)()
                    for p in relatives),
                "T06_CI_INSTALL_PATH_CHANGED_AFTER_PREFLIGHT_HOLD")
        installed=run([str(SETUP),"/S"],260)
        report["installer_lifecycle"]["install"]=installed
        require(installed["code"]==0 and install.is_dir(),"T06_NSIS_SILENT_INSTALL_FAILED")
        mark=install/"nox-p01-owned.txt"
        wpf=install/"NOX.P01.Shell.exe"
        backend=install/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"
        require(regular(mark) and mark.read_text("utf-8-sig").strip()=="NOXHELION.P01 V16" and
                regular(wpf) and regular(backend) and
                sha(wpf)==evidence["wpf_sha256"] and
                sha(backend)==evidence["backend_sha256"],
                "T06_INSTALLED_BINARY_OR_OWNERSHIP_SHA_HOLD")
        report["installed_wpf_sha256"]=sha(wpf)
        report["installed_backend_sha256"]=sha(backend)
        verify_result=run(["powershell.exe","-NoProfile","-NonInteractive",
                      "-ExecutionPolicy","Bypass","-File",str(verify),
                      "-Root",str(install),
                      "-Manifest",str(install/"payload.sha256.json"),
                      "-AllowInstalledMetadata"],130)
        report["installer_lifecycle"]["verify"]=verify_result
        require(verify_result["code"]==0,"T06_INSTALLED_OWNER_MANIFEST_VERIFY_FAILED")
        report["installer_lifecycle"]["native_ipc"]=framed(
            backend,OUTPUT/"native-ipc-data",report)
        # All approved HOME pixels remain frozen before the native GUI probe.
        approved={"home.png":"382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",
                  "core01.png":"343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97"}
        for name,expected in approved.items():
            actual=install/"Assets"/name
            require(regular(actual) and sha(actual)==expected,
                    "T06_APPROVED_HOME_CORE_SOURCE_SHA_DRIFT:"+name)
        report["original_home_and_core01_sha_verified"]=True
        gui=live_original_wpf_probe(wpf,Path(local))
        report["installer_lifecycle"]["original_wpf_gui"]=gui
        require(gui["new_nav_ok"] and gui["new_python_ipc_handshake"],
                "T06_ORIGINAL_WPF_WEBVIEW2_AND_PYTHON_RUNTIME_NOT_PROVEN")
        # User data lives OUTSIDE the program install location.
        persistent=Path(local)/"NOX_HELION"/"P01"
        require(plain_parents(persistent,local_base),
                "T06_USER_DATA_REPARSE_ANCESTOR_HOLD")
        persistent.mkdir(parents=True,exist_ok=True)
        marker=persistent/("m1-e07-no-loss-"+ci_run_id+".txt")
        require(not marker.exists() and not marker.is_symlink() and
                not getattr(marker,"is_junction",lambda:False)(),
                "T06_USER_DATA_PROOF_COLLISION")
        signature=b"NOX_M1_PERSISTENT_STATE_NOLOSS\n"
        marker.write_bytes(signature)
        update=run([str(SETUP),"/S"],250)
        report["installer_lifecycle"]["update"]=update
        backup=Path(str(install)+".__p01_previous")
        require(update["code"]==0 and backup.is_dir(),
                "T06_ORIGINAL_NSIS_UPDATE_BACKUP_HOLD")
        require(sha(wpf)==evidence["wpf_sha256"] and
                marker.read_bytes()==signature,
                "T06_UPDATE_MUST_PRESERVE_BINARY_AND_DATA")
        rollback=run([str(SETUP),"/S","/ROLLBACK"],250)
        report["installer_lifecycle"]["rollback"]=rollback
        require(rollback["code"]==0 and sha(wpf)==evidence["wpf_sha256"] and
                marker.read_bytes()==signature,
                "T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD")
        owned_files=owned_payload_paths(
            install,strict_receipt(install/"payload.sha256.json",
                                  "T06_UNINSTALL_INSTALLED_INVENTORY_JSON_HOLD"))
        uninstall=install/"Uninstall.exe"
        require(regular(uninstall),"T06_ORIGINAL_UNINSTALLER_MISSING")
        uninstalled=run([str(uninstall),"/S"],220)
        report["installer_lifecycle"]["uninstall"]=uninstalled
        require(uninstalled["code"]==0,"T06_CONSERVATIVE_UNINSTALL_EXIT_HOLD")
        verify_original_uninstall(install,owned_files)
        report["installer_lifecycle"]["uninstall_owned_files_checked"]=len(owned_files)
        report["installer_lifecycle"]["uninstall_registry_views_checked"]=2
        require(marker.is_file() and marker.read_bytes()==signature,
                "T06_ORIGINAL_NSIS_UNINSTALL_USER_DATA_LOSS")
        report["phase"]="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"
        print("T06_SAME_VM_INSTALL_NATIVE_UNINSTALL_PASS",
              evidence["setup_sha256"],flush=True)
        code=0
    except Exception as exc:
        report["reason"]=str(exc)[:260]
        print("T06_SAME_VM_INSTALLED_SMOKE_HOLD",report["reason"],flush=True)
    finally:
        report["elapsed_seconds"]=round(time.monotonic()-started,2)
        OUTPUT.mkdir(parents=True,exist_ok=True)
        with NSIS_PROOF.open("x",encoding="utf-8") as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2)
    return code

if __name__=="__main__":
    raise SystemExit(main())
