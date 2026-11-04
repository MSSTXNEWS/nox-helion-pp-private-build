"""Independent NOX HELION EXPRESS Windows same-Setup E07 diagnostics.

Run only on an authorized ephemeral GitHub-hosted Windows VM. Fails closed,
never deletes unknown files, and never claims actual local model inference.
The source/Setup pins are immutable, while this test has its own CI run ID.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

SOURCE_SHA = "4249188fbce7242ace05a536f26121096746b52a"
SETUP_SHA = "a5097c11f60d0906dcc96984dcbeab13d7f07307a02651fa4c3c1a2bae53ccde"
SETUP_SIZE = 87331353
RECEIPT_SCHEMA = "nox.express.onehost.same-sha.v1"
PROTOCOL = "NOX-P02-NATIVE-v1"

class Hold(RuntimeError):
    """Fail-closed gate with a bounded public reason code."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Hold(code)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1 << 20)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def clean_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()


def clean_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()


def run(args: list[str], *, limit: int) -> int:
    result = subprocess.run(args, check=False, timeout=limit,
                            capture_output=True, cwd=os.environ["RUNNER_TEMP"])
    return result.returncode


def setup_lock(setup: Path, receipt: Path) -> dict:
    require(clean_file(setup) and clean_file(receipt), "E07_SOURCE_ARTIFACT_NOT_REGULAR")
    with receipt.open("r", encoding="utf-8-sig") as f:
        proof = json.load(f)
    require(type(proof) is dict and proof.get("schema") == RECEIPT_SCHEMA and
            proof.get("source_commit") == SOURCE_SHA and
            proof.get("setup_sha256") == SETUP_SHA and
            proof.get("setup_bytes") == SETUP_SIZE and
            proof.get("physical_setup_built") is True and
            proof.get("release_accepted") is False and
            proof.get("independent_e07") == "NOT_RUN", "E07_SOURCE_RECEIPT_HOLD")
    require(setup.stat().st_size == SETUP_SIZE and sha256(setup) == SETUP_SHA,
            "E07_SETUP_SHA_HOLD")
    with setup.open("rb") as f:
        header = f.read(4096)
    offset = struct.unpack_from("<I", header, 0x3c)[0]
    require(header[:2] == b"MZ" and offset <= len(header)-6 and
            header[offset:offset+4] == b"PE\0\0", "E07_SETUP_WINDOWS_PE_HOLD")
    return {"source_sha": SOURCE_SHA, "setup_sha256": SETUP_SHA,
            "setup_bytes": SETUP_SIZE, "pe_machine":hex(struct.unpack_from("<H",header,offset+4)[0])}


def manifest_owner(install: Path) -> tuple[dict, tuple[Path, ...]]:
    require(clean_dir(install), "E07_INSTALLED_DIR_HOLD")
    owner = install / "nox-p01-owned.txt"
    manifest = install / "payload.sha256.json"
    require(clean_file(owner) and clean_file(manifest) and
            owner.read_text(encoding="utf-8-sig").strip() == "NOXHELION.P01 V16",
            "E07_INSTALLED_OWNER_MARKER_HOLD")
    m = json.loads(manifest.read_text(encoding="utf-8-sig"))
    require(type(m) is dict and m.get("schema") == "NOX_P01_PAYLOAD_SHA256_V1"
            and m.get("entrypoint") == "NOX.P01.Shell.exe" and
            type(m.get("files")) is list and 1 <= len(m["files"]) <= 50000,
            "E07_INSTALLED_MANIFEST_SCHEMA_HOLD")
    seen = set()
    files = []
    root_resolved = install.resolve(strict=True)
    for entry in m["files"]:
        require(type(entry) is dict and type(entry.get("path")) is str and
                type(entry.get("sha256")) is str and
                re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) is not None and
                type(entry.get("bytes")) is int and entry["bytes"] >= 0,
                "E07_MANIFEST_BAD_ENTRY")
        rel = entry["path"].replace("/", "\\")
        parts = tuple(rel.replace("\\", "/").split("/"))
        require(bool(parts) and all(v not in ("", ".", "..") for v in parts)
                and not Path(rel).is_absolute() and ":" not in rel,
                "E07_MANIFEST_UNSAFE_PATH")
        folded = rel.casefold()
        require(folded not in seen, "E07_MANIFEST_DUPLICATE")
        seen.add(folded)
        path = install.joinpath(*parts)
        require(all(not parent.is_symlink() and
                    not getattr(parent, "is_junction", lambda: False)()
                    for parent in (path, *path.parents) if parent != root_resolved) and
                clean_file(path) and path.stat().st_size == entry["bytes"] and
                path.resolve(strict=True).is_relative_to(root_resolved) and
                sha256(path) == entry["sha256"], "E07_INSTALLED_FILE_SHA_HOLD")
        files.append(path)
    return m, tuple(files)


def framed_backend(backend: Path, scratch: Path) -> dict:
    require(clean_file(backend), "E07_NATIVE_EXE_MISSING")
    request = {"protocol":PROTOCOL, "requestId":"0123456789abcdef0123456789abcdef",
               "runId":"NOX-E07-INDEPENDENT-SHA-PIN", "route":"models.installed",
               "payload":{}}
    raw = json.dumps(request,separators=(",", ":")).encode("utf-8")
    wire = struct.pack(">I",len(raw)) + raw
    proc = subprocess.run([str(backend),"--native-stdio","--run-id",request["runId"],
                           "--data-dir",str(scratch)],input=wire,
                          capture_output=True,timeout=105,cwd=str(backend.parent))
    require(proc.returncode == 0 and len(proc.stdout) >= 5,
            "E07_NATIVE_PROCESS_OR_FRAME_HOLD")
    n = struct.unpack(">I",proc.stdout[:4])[0]
    require(1 <= n <= 1048576 and len(proc.stdout) == 4+n,
            "E07_NATIVE_FRAME_LENGTH_HOLD")
    answer = json.loads(proc.stdout[4:].decode("utf-8"))
    require(type(answer) is dict and
            all(answer.get(k)==request[k] for k in ("protocol","runId","requestId")),
            "E07_NATIVE_IPC_IDENTITY_HOLD")
    status = answer.get("status")
    if status == "OK":
        require(type(answer.get("result")) is dict and
                type(answer["result"].get("models")) is list,
                "E07_NATIVE_MODEL_LIST_INVALID")
        return {"ipc":"PASS", "provider":"AVAILABLE",
                "models_reported":len(answer["result"]["models"]),
                "real_model_inference":"NOT_TESTED"}
    require(status == "HOLD" and answer.get("errorCode")=="NATIVE_PROVIDER_HOLD" and
            answer.get("result") is None,"E07_NATIVE_UNEXPECTED_PROVIDER_HOLD")
    return {"ipc":"PASS", "provider":"OFFLINE_HOLD", "models_reported":0,
            "real_model_inference":"NOT_TESTED"}


_WPF_EVENTS = (
    "INIT_BEGIN", "NAV_START", "NAV_OK", "NAV_FAIL", "BLOCK_NAV",
    "WEBVIEW_PROCESS_FAILED", "P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK",
    "INIT_ERROR", "P02_ORIGINAL_NATIVE_HOLD",
)
_WPF_FATAL = frozenset(("NAV_FAIL", "BLOCK_NAV", "WEBVIEW_PROCESS_FAILED",
                         "INIT_ERROR", "P02_ORIGINAL_NATIVE_HOLD"))


def wpf_marker_flags(window: str) -> dict[str, bool]:
    """Strict bracket-prefixed complete events, never substring success."""
    flags = {name: False for name in _WPF_EVENTS}
    for line in window.splitlines():
        if not line.startswith("["):
            continue
        prefix, sep, text = line.partition("] ")
        if not sep or not 2 <= len(prefix) <= 160:
            continue
        code = text.split(" ", 1)[0].rstrip("\r")
        if code in flags:
            flags[code] = True
    return flags


def gui_hwnd(shell: Path, local: Path) -> dict:
    """Independently prove fresh WPF/WebView2 NAV_OK+native handshake+HWND."""
    require(clean_file(shell), "E07_WPF_SHELL_MISSING")
    log = local / "NOX_HELION/P01/logs/shell.log"
    initial = log.stat() if clean_file(log) else None
    identity = (initial.st_dev, initial.st_ino) if initial else None
    offset = initial.st_size if initial else 0
    boundary = ""
    flags = {name: False for name in _WPF_EVENTS}
    proc = subprocess.Popen([str(shell)], cwd=str(shell.parent),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    handle = None
    started = None
    try:
        user32 = ctypes.windll.user32
        enum_proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def inspect(hwnd, _):
            nonlocal handle
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == proc.pid and user32.IsWindowVisible(hwnd):
                handle = int(hwnd)
                return False
            return True
        callback = enum_proto(inspect)
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline and proc.poll() is None:
            if clean_file(log):
                st = log.stat()
                now_identity = (st.st_dev, st.st_ino)
                if identity is None:
                    identity = now_identity
                require(now_identity == identity and st.st_size >= offset,
                        "E07_WPF_LOG_REPLACEMENT_HOLD")
                if st.st_size > offset:
                    with log.open("rb") as f:
                        f.seek(offset)
                        block = f.read(min(65536, st.st_size - offset))
                    offset += len(block)
                    window = boundary + block.decode("utf-8", errors="replace")
                    complete, delim, tail = window.rpartition("\n")
                    if delim:
                        fresh = wpf_marker_flags(complete)
                        for name in flags:
                            flags[name] = flags[name] or fresh[name]
                        boundary = tail[-4096:]
                    else:
                        boundary = window[-4096:]
            require(not any(flags[name] for name in _WPF_FATAL),
                    "E07_WPF_NAVIGATION_FATAL_HOLD")
            handle = None
            user32.EnumWindows(callback, 0)
            ready = (handle is not None and flags["NAV_OK"] and
                     flags["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"] and
                     not flags["NAV_FAIL"] and proc.poll() is None)
            if ready:
                if started is None:
                    started = time.monotonic()
                if time.monotonic() - started >= 8:
                    require(user32.IsWindow(handle), "E07_WPF_HWND_REPLACED_HOLD")
                    return {"gui_visible_hwnd": "PASS", "stable_seconds": 8,
                            "webview_navigation": "PASS", "shell_native_ipc": "PASS",
                            "independent_webview_log": "CURRENT_PROCESS_FRESH_NAV_AND_IPC",
                            "visual_e07": "HOLD"}
            else:
                started = None
            time.sleep(0.45)
        raise Hold("E07_WPF_FRESH_NAV_OR_HWND_TIMEOUT")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                               timeout=15, capture_output=True, check=False)


def lifecycle(setup: Path, result: dict) -> None:
    local = Path(os.environ["LOCALAPPDATA"])
    require(clean_dir(local), "E07_LOCALAPPDATA_UNTRUSTED")
    base = local / "Programs"
    install = base / "NOX HELION"
    stage = Path(str(install)+".__p01_stage")
    previous = Path(str(install)+".__p01_previous")
    saved = Path(str(install)+".__p01_rollback_saved")
    # Never touch an existing installation or recovery slot.
    require(all(not x.exists() and not x.is_symlink() for x in
                (install, stage, previous, saved)), "E07_VM_NOT_FRESH_SKIP")
    userdata = local/"NOX_HELION"/"P01"
    require(all(not p.is_symlink() and not getattr(p,"is_junction",lambda:False)()
                for p in (userdata,*userdata.parents)), "E07_USERDATA_REPARSE_HOLD")
    userdata.mkdir(parents=True,exist_ok=True)
    user_marker = userdata/"e07-independent-no-loss.txt"
    require(not user_marker.exists(), "E07_USERDATA_MARKER_COLLISION")
    signature=b"NOX_E07_USER_DATA_PRESERVED\n"
    user_marker.write_bytes(signature)
    require(run([str(setup),"/S"],limit=300)==0, "E07_NSIS_FRESH_INSTALL_EXIT_HOLD")
    m, owned = manifest_owner(install)
    result["checks"]["install_and_manifest"] = {"status":"PASS", "files_sha256":len(owned)}
    native = framed_backend(install/"Backend"/"NOX_HELION_PRIVATE_CANDIDATE.exe",
                            Path(os.environ["RUNNER_TEMP"])/"nox-e07-native-data")
    result["checks"]["installed_native_ipc"] = native
    result["checks"]["installed_gui"] = gui_hwnd(install/"NOX.P01.Shell.exe",local)
    require(run([str(setup),"/S"],limit=300)==0 and clean_dir(previous),
            "E07_NSIS_UPDATE_HOLD")
    manifest_owner(previous)
    require(user_marker.read_bytes()==signature,"E07_UPDATE_USER_DATA_LOSS")
    result["checks"]["update"]={"status":"PASS","backup_verified":True}
    require(run([str(setup),"/S","/ROLLBACK"],limit=300)==0 and clean_dir(saved),
            "E07_NSIS_ROLLBACK_HOLD")
    manifest_owner(saved)
    _, owned = manifest_owner(install)
    require(user_marker.read_bytes()==signature,"E07_ROLLBACK_USER_DATA_LOSS")
    result["checks"]["rollback"]={"status":"PASS","restored_verified":True}
    uninstaller=install/"Uninstall.exe"
    require(clean_file(uninstaller),"E07_UNINSTALL_EXE_MISSING")
    require(run([str(uninstaller),"/S"],limit=240)==0,"E07_NSIS_UNINSTALL_EXIT_HOLD")
    tracked=owned+(install/"payload.sha256.json",install/"nox-p01-owned.txt",uninstaller)
    deadline=time.monotonic()+180
    while any(p.exists() or p.is_symlink() for p in tracked) and time.monotonic()<deadline:
        time.sleep(0.3)
    require(not any(p.exists() or p.is_symlink() for p in tracked) and
            not install.is_dir(),"E07_NSIS_UNINSTALL_RESIDUE_HOLD")
    require(user_marker.is_file() and user_marker.read_bytes()==signature,
            "E07_UNINSTALL_USER_DATA_LOSS")
    result["checks"]["uninstall"]={"status":"PASS", "owned_files_absent":len(owned),
                                    "userdata_preserved":True}
    require(clean_dir(saved),"E07_BACKUP_POLICY_VIOLATED")
    result["checks"]["backup_retention"]={"status":"PASS","saved_rollback_slot_retained":True}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--artifact-dir",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    result={"schema":"NOX-EXPRESS-INDEPENDENT-E07-CANDIDATE-v1",
            "source_sha":SOURCE_SHA,"setup_sha256":SETUP_SHA,
            "checks":{},"release_accepted":False,"independent_e07":"HOLD",
            "error":"NOT_RUN"}
    try:
        require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_HOST_NOT_AUTHORIZED")
        source = args.artifact_dir
        setup=source/"NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe"
        receipt=source/"BUILD_RECEIPT.json"
        result["checks"]["artifact"] = setup_lock(setup,receipt)
        lifecycle(setup,result)
        # Model inference, visual click navigation and independent screenshot
        # remain mandatory for release; do not forge them from HWND and IPC.
        result["error"]="E07_REAL_MODEL_AND_VISUAL_ACCEPTANCE_NOT_COMPLETE"
    except (Hold,FileNotFoundError,ValueError,TimeoutError,
            subprocess.TimeoutExpired,PermissionError) as exc:
        result["error"]=(str(exc) if isinstance(exc,Hold) else
                          "E07_"+type(exc).__name__.upper()+"_HOLD")[:140]
    except Exception as exc:
        # Never leak Windows paths or untrusted process output into logs.
        result["error"]="E07_UNEXPECTED_"+type(exc).__name__.upper()+"_HOLD"
    finally:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2),encoding="utf-8")
        print("NOX_E07_INDEPENDENT_DIAGNOSTIC",result["error"],flush=True)
    return 0 if result["independent_e07"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
