"""Independent NOX HELION EXPRESS Windows same-Setup E07 diagnostics.

Run only on an authorized ephemeral GitHub-hosted Windows VM. Fails closed,
never deletes unknown files, and never claims actual local model inference.
The source/Setup pins are immutable, while this test has its own CI run ID.
"""
from __future__ import annotations

import argparse
import importlib.util
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import struct
import sqlite3
from contextlib import closing
import subprocess
import sys
import time

SOURCE_SHA = "c35c1d330b36900c61d41f65661c535dcd6fc78a"
SETUP_SHA = "af87a6181dee5e04d2a83bc33e738aec16534fa32bc407b40c009ab169129879"
SETUP_SIZE = 169590852
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



def installed_file_sha_locked(path: Path, root: Path, expected_size: int, expected_digest: str,
                              *, return_pe_header: bool = False) -> str | tuple[str, bytes]:
    """Bind an installed owned-file SHA to one regular descriptor and the same path identity.

    Do not trust a pathname hash after a separate stat/resolve: a same-byte file
    replacement between the lookup and descriptor opening would pass that hash.
    """
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    def descriptor_identity(info):
        # Windows os.fstat(fd).st_ctime_ns need not agree with pathname lstat()
        # for an unchanged file (observed physical E07 run 41778686243).
        # Preserve strict pathname ctime before/after AND file ID/volume/size/
        # mtime before/open/after. Never accept swapped names or file contents.
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    def allowed_path():
        return (path.is_file() and not path.is_symlink() and
                not getattr(path, "is_junction", lambda: False)() and
                path.resolve(strict=True).is_relative_to(root) and
                all(not parent.is_symlink() and
                    not getattr(parent, "is_junction", lambda: False)()
                    for parent in path.parents if parent != root and parent.is_relative_to(root)))
    try:
        if not allowed_path():
            raise Hold("E07_INSTALLED_FILE_SHA_HOLD")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise Hold("E07_INSTALLED_FILE_SHA_HOLD")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise Hold("E07_INSTALLED_FILE_OPEN_NONREGULAR_HOLD")
            # Bounded, privacy-safe failure kind: never return local names or IDs.
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            mismatch = [field.removeprefix("st_").upper() for field in fields
                        if getattr(before, field) != getattr(opened, field)]
            if mismatch:
                raise Hold("E07_INSTALLED_FILE_OPEN_IDENTITY_HOLD:" + ",".join(mismatch))
            digest = hashlib.sha256()
            header = bytearray()
            while block := os.read(fd, 1048576):
                # Capture PE header from the SAME descriptor as all SHA bytes.
                # Never reopen a mutable pathname after source identity checks.
                if return_pe_header and len(header) < 4096:
                    header.extend(block[:4096 - len(header)])
                digest.update(block)
            if descriptor_identity(opened) != descriptor_identity(os.fstat(fd)):
                raise Hold("E07_INSTALLED_FILE_FD_MUTATED_HOLD")
            after = path.lstat()
            if identity(before) != identity(after):
                raise Hold("E07_INSTALLED_FILE_PATH_MUTATED_HOLD")
            if descriptor_identity(opened) != descriptor_identity(after):
                raise Hold("E07_INSTALLED_FILE_FD_PATH_MISMATCH_HOLD")
            if not allowed_path():
                raise Hold("E07_INSTALLED_FILE_REPARSE_OR_ESCAPE_HOLD")
            if digest.hexdigest() != expected_digest:
                raise Hold("E07_INSTALLED_FILE_SHA_HOLD")
            verified = digest.hexdigest()
            return (verified, bytes(header)) if return_pe_header else verified
        finally:
            os.close(fd)
    except OSError as exc:
        # Public errno only: preserve privacy, avoid exposing installed paths.
        raise Hold("E07_INSTALLED_FILE_IO_" + str(exc.errno if type(exc.errno) is int else "UNKNOWN") + "_HOLD") from None

def run(args: list[str], *, limit: int) -> int:
    result = subprocess.run(args, check=False, timeout=limit,
                            capture_output=True, cwd=os.environ["RUNNER_TEMP"])
    return result.returncode


E06_BUILD_ID = "NOX-V16-4a0070cdb51d1d2d37a8d295"
ORIGINAL_ZIP_SHA = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"


def _read_locked_e06_json(path: Path) -> dict:
    require(clean_file(path) and path.stat().st_size <= 1048576,
            "E07_E06_RECEIPT_NOT_REGULAR")
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise Hold("E07_E06_RECEIPT_DUPLICATE_FIELD")
            obj[key] = value
        return obj
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream, object_pairs_hook=unique_pairs,
                parse_constant=lambda unused: (_ for _ in ()).throw(
                    Hold("E07_E06_RECEIPT_NONFINITE_NUMBER")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Hold("E07_E06_RECEIPT_INVALID_JSON") from None
    require(type(data) is dict, "E07_E06_RECEIPT_SCHEMA_HOLD")
    return data


# Physical frozen E06 c35c1d33 / Setup af87a618 receipt observed 1004.
# A future SetupSHA MUST explicitly pin its OWN manifest count after physical
# verification; neither JSON claims nor source-tree size can change this value.
FROZEN_E06_OWNED_COUNT = 1004


def samevm_lifecycle_verified(
    stages: object, *, expected_owned_files: int = FROZEN_E06_OWNED_COUNT
) -> bool:
    """Fail closed on exact frozen E06 owned count and five real exit codes.

    E07's next physical candidate may change the source-pinned count only
    together with its independently frozen source/Setup SHA+BuildID.
    """
    if (type(stages) is not dict or type(expected_owned_files) is not int or
            not 1 <= expected_owned_files <= 4096):
        return False
    return (type(stages.get("uninstall_owned_files_checked")) is int
            and stages["uninstall_owned_files_checked"] == expected_owned_files
            and all(type(stages.get(name)) is dict and
                    type(stages[name].get("code")) is int and
                    stages[name]["code"] == 0
                    for name in ("install", "verify", "update", "rollback", "uninstall")))


def setup_lock(setup: Path, receipt: Path) -> dict:
    """Pin physical latest E06 Setup to three same-identity receipts, then verify bytes.

    Prior E06 same-VM lifecycle is NOT independent E07; lifecycle() must rerun.
    """
    require(clean_file(setup) and clean_file(receipt), "E07_SOURCE_ARTIFACT_NOT_REGULAR")
    require(setup.parent == receipt.parent and receipt.name == "E07_BUILT_HANDOFF.json",
            "E07_E06_HANDOFF_PATH_HOLD")
    handoff = _read_locked_e06_json(receipt)
    diagnostic = _read_locked_e06_json(receipt.parent/"ONEHOST_DIAGNOSTIC_RECEIPT.json")
    smoke = _read_locked_e06_json(receipt.parent/"T06_INSTALLED_SMOKE.json")
    require(handoff.get("schema") == "NOX_V16_E07_IMMUTABLE_HANDOFF_V1" and
            handoff.get("source_commit_sha1") == SOURCE_SHA and
            handoff.get("build_id") == E06_BUILD_ID and
            handoff.get("phase") == "BUILT" and
            handoff.get("original_zip_sha256") == ORIGINAL_ZIP_SHA and
            handoff.get("source_files") == 729 and
            handoff.get("source_receipts_729_parity_verified") is True and
            handoff.get("setup_sha256") == SETUP_SHA and
            type(handoff.get("independent_e07_cases_accepted")) is int and
            handoff["independent_e07_cases_accepted"] == 0 and
            handoff.get("release_accepted") is False and
            handoff.get("status") == "PENDING_E07_INDEPENDENT_SAME_SHA_QA",
            "E07_E06_HANDOFF_IDENTITY_HOLD")
    require(diagnostic.get("schema") == "NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1" and
            diagnostic.get("source_commit_sha1") == SOURCE_SHA and
            diagnostic.get("installer_sha256") == SETUP_SHA and
            type(diagnostic.get("installer_bytes")) is int and
            diagnostic["installer_bytes"] == SETUP_SIZE and
            diagnostic.get("release_accepted") is False and
            diagnostic.get("status") == "WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED",
            "E07_E06_DIAGNOSTIC_IDENTITY_HOLD")
    stages = smoke.get("installer_lifecycle")
    require(smoke.get("schema") == "NOX-T06-INSTALLED-SMOKE-v1" and
            smoke.get("phase") == "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07" and
            smoke.get("build_id") == E06_BUILD_ID and
            smoke.get("setup_sha256") == SETUP_SHA and
            smoke.get("release_accepted") is False and
            smoke.get("e07_independent_acceptance") == "NOT_RUN" and
            samevm_lifecycle_verified(stages),
            "E07_E06_SAMEVM_RECEIPT_HOLD")
    require(clean_dir(setup.parent), "E07_SETUP_PARENT_REPARSE_HOLD")
    locked_sha, header = installed_file_sha_locked(
        setup, setup.parent.resolve(strict=True), SETUP_SIZE, SETUP_SHA,
        return_pe_header=True)
    require(locked_sha == SETUP_SHA, "E07_SETUP_SHA_HOLD")
    require(len(header) >= 64 and header[:2] == b"MZ", "E07_SETUP_WINDOWS_PE_HOLD")
    offset = struct.unpack_from("<I", header, 0x3c)[0]
    require(offset <= len(header)-6 and header[offset:offset+4] == b"PE\0\0",
            "E07_SETUP_WINDOWS_PE_HOLD")
    return {"source_sha":SOURCE_SHA,"setup_sha256":SETUP_SHA,
            "setup_bytes":SETUP_SIZE,"pe_machine":hex(struct.unpack_from("<H",header,offset+4)[0]),
            "build_id":E06_BUILD_ID,"e06_samevm_pass_not_e07":True}



# Frozen ORIGINAL OneHost E06 Setup from run 41785340462 (not D02).
# All three real producer receipts and binary/source SHA must agree.
ORIGINAL_E06_SOURCE = "8e938107519fc2ca33b6024884c8410c2803e3ba"
ORIGINAL_E06_SETUP_SHA = "d468e00b31fea04b6d726cc077f65048d8f132cd5f0bb51bf30c6241ce139c5d"
ORIGINAL_E06_SETUP_BYTES = 87342506
ORIGINAL_E06_SOURCE_ZIP_SHA = "6b2b75a4050f91f9962483b8a199a8670d1a71023501240727d55fb75c38eb67"
ORIGINAL_E06_OWNED_FILES = 485

def setup_lock_original(setup: Path, base: Path) -> dict:
    """Fail closed on unmodified original E06 physical candidate, NOT E07 success."""
    require(clean_dir(base) and setup.parent == base and
            setup.name == "NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe",
            "E07_ORIGINAL_CANDIDATE_PATH_HOLD")
    build = _read_locked_e06_json(base/"BUILD_RECEIPT.json")
    candidate = _read_locked_e06_json(base/"ONEHOST_CANDIDATE_RECEIPT.json")
    smoke = _read_locked_e06_json(base/"T06_INSTALLED_SMOKE.json")
    require(build.get("schema")==RECEIPT_SCHEMA and
            build.get("source_commit")==ORIGINAL_E06_SOURCE and
            build.get("physical_setup_built") is True and
            build.get("setup_sha256")==ORIGINAL_E06_SETUP_SHA and
            type(build.get("setup_bytes")) is int and
            build["setup_bytes"]==ORIGINAL_E06_SETUP_BYTES and
            build.get("build_outcome")=="success" and
            build.get("classification")=="DIAGNOSTIC_CANDIDATE_NOT_RELEASE" and
            build.get("release_accepted") is False and
            build.get("independent_e07")=="NOT_RUN",
            "E07_ORIGINAL_BUILD_RECEIPT_HOLD")
    require(candidate.get("schema")=="NOX-E06-ONEHOST-CANDIDATE-v1" and
            candidate.get("source_git_sha")==ORIGINAL_E06_SOURCE and
            candidate.get("setup_sha256")==ORIGINAL_E06_SETUP_SHA and
            type(candidate.get("setup_bytes")) is int and
            candidate["setup_bytes"]==ORIGINAL_E06_SETUP_BYTES and
            candidate.get("backend_native_stdio_windows_exe_smoke")=="PASS" and
            candidate.get("wpf_source_compilation")=="PASS" and
            candidate.get("wpf_installed_interactive_qa")=="NOT_RUN" and
            candidate.get("e07")=="NOT_ACCEPTED" and
            candidate.get("release_accepted") is False,
            "E07_ORIGINAL_ONEHOST_RECEIPT_HOLD")
    home=candidate.get("original_home_provenance")
    require(type(home) is dict and home.get("five_primary_installed_uia")=="NOT_RUN" and
            home.get("release_accepted") is False and
            type(home.get("published_home_bytes")) is int and
            home["published_home_bytes"]==99192 and
            type(home.get("published_home_sha256")) is str and
            re.fullmatch(r"[a-f0-9]{64}",home["published_home_sha256"]) is not None,
            "E07_ORIGINAL_HOME_RECEIPT_HOLD")
    require(smoke.get("schema")=="NOX-T06-INSTALLED-SMOKE-v1" and
            smoke.get("phase")=="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07" and
            smoke.get("environment")=="GITHUB_WINDOWS_EPHEMERAL_BRIDGE_NOT_E07" and
            smoke.get("setup_sha256")==ORIGINAL_E06_SETUP_SHA and
            smoke.get("installed_wpf_sha256")==candidate.get("wpf_sha256") and
            smoke.get("installed_backend_sha256")==candidate.get("backend_sha256") and
            smoke.get("manifest_sha256")==candidate.get("manifest_sha256") and
            smoke.get("e07_independent_acceptance")=="NOT_RUN" and
            smoke.get("release_accepted") is False and
            type(smoke.get("manifest_files_checked")) is int and
            smoke["manifest_files_checked"]==ORIGINAL_E06_OWNED_FILES and
            samevm_lifecycle_verified(smoke.get("installer_lifecycle"),
                expected_owned_files=ORIGINAL_E06_OWNED_FILES),
            "E07_ORIGINAL_SAMEVM_RECEIPT_HOLD")
    source=base/("NOX_HELION_EXPRESS_SOURCE_"+ORIGINAL_E06_SOURCE+".zip")
    require(clean_file(source) and sha256(source)==ORIGINAL_E06_SOURCE_ZIP_SHA,
            "E07_ORIGINAL_SOURCE_ZIP_SHA_HOLD")
    require(clean_file(setup) and setup.stat().st_size==ORIGINAL_E06_SETUP_BYTES,
            "E07_ORIGINAL_SETUP_BYTES_HOLD")
    checked,header=installed_file_sha_locked(setup,base.resolve(strict=True),
        ORIGINAL_E06_SETUP_BYTES,ORIGINAL_E06_SETUP_SHA,return_pe_header=True)
    require(checked==ORIGINAL_E06_SETUP_SHA and len(header)>=64 and
            header[:2]==b"MZ", "E07_ORIGINAL_SETUP_PE_HOLD")
    offset=struct.unpack_from("<I",header,0x3c)[0]
    require(offset<=len(header)-6 and header[offset:offset+4]==bytes.fromhex("50450000"),
            "E07_ORIGINAL_SETUP_PE_HOLD")
    return {"source_sha":ORIGINAL_E06_SOURCE,
            "setup_sha256":ORIGINAL_E06_SETUP_SHA,
            "setup_bytes":ORIGINAL_E06_SETUP_BYTES,
            "source_zip_sha256":ORIGINAL_E06_SOURCE_ZIP_SHA,
            "build_id":"NOT_PROVIDED_IN_E06_RECEIPT",
            "e06_samevm_pass_not_e07":True,
            "owned_count_source_pinned":ORIGINAL_E06_OWNED_FILES,
            "five_primary_installed_uia":"NOT_RUN",
            "model":"PROVIDER_OFFLINE_HOLD",
            "release_accepted":False}

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
                installed_file_sha_locked(path, root_resolved, entry["bytes"], entry["sha256"]) == entry["sha256"], "E07_INSTALLED_FILE_SHA_HOLD")
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


_WPF_WITNESS_PATH = Path(__file__).resolve().parents[1] / "e06" / "t06_windows_hwnd_witness.py"


_UIA_MAIN_BUTTONS = ("CHAT", "INSTALL", "MODELS", "LEARN", "REPORTS")

def classify_primary_button_names(labels: list[str]) -> dict:
    """Evidence of button presence only, never a click or inference PASS."""
    require(type(labels) is list and len(labels) <= 2048 and
            all(type(x) is str and len(x) <= 128 for x in labels),
            "E07_UIA_UNTRUSTED_LABELS")
    found = set()
    for label in labels:
        label = label.strip().lstrip("✦★•").strip().upper()
        if label in _UIA_MAIN_BUTTONS:
            found.add(label)
    missing = [name for name in _UIA_MAIN_BUTTONS if name not in found]
    return {"status": "HOLD" if missing else "PASS",
            "buttons_present": [v for v in _UIA_MAIN_BUTTONS if v in found],
            "buttons_missing": missing,
            "proof": "VISIBLE_ENABLED_UIA_BUTTONS_ONLY", "actions_invoked": 0}


def classify_primary_uia_evidence(response: dict) -> dict:
    """Bounded UIA tree diagnostics; text/non-button evidence can NEVER be a button PASS."""
    require(type(response) is dict and response.get("schema") == "NOX-E07-UIA-V1",
            "E07_UIA_BAD_SCHEMA_HOLD")
    total, scanned, targets = (response.get("treeCount"), response.get("treeScanned"),
                               response.get("targetTypes"))
    require(type(total) is int and 0 <= total <= 100000 and
            type(scanned) is int and 0 <= scanned <= min(total, 2048) and
            type(targets) is list and len(targets) <= 64 and
            all(type(item) is str and re.fullmatch(
                r"(CHAT|INSTALL|MODELS|LEARN|REPORTS)\|"
                r"(ControlType\.(Button|Text|Document|Hyperlink|Custom|Group|Pane|Edit)|Other)\|"
                r"(VISIBLE_ENABLED|OFFSCREEN|DISABLED|TOO_SMALL)", item)
                for item in targets), "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD")
    require(len(targets) <= scanned, "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD")
    result = classify_primary_button_names(response.get("labels"))
    # Chromium UIA providers can enumerate a real visible Button in unfiltered
    # descendants even when the separate Button property-filter returns [].
    # These are the SAME HWND-rooted physical UIA elements, NOT text/Custom or
    # an inferred click. Only the exact visible+enabled Button role is admitted.
    witnessed = {entry.split("|", 1)[0] for entry in targets
                 if entry.endswith("|ControlType.Button|VISIBLE_ENABLED")}
    found = set(result["buttons_present"]) | witnessed
    result.update({"status": "PASS" if len(found) == len(_UIA_MAIN_BUTTONS) else "HOLD",
                   "buttons_present": [v for v in _UIA_MAIN_BUTTONS if v in found],
                   "buttons_missing": [v for v in _UIA_MAIN_BUTTONS if v not in found],
                   "proof": "SAME_ROOT_UIA_VISIBLE_ENABLED_BUTTON_PRESENCE_ONLY",
                   "actions_invoked": 0,
                   "uia_tree_total": total, "uia_tree_scanned": scanned,
                   "uia_known_labels_by_role": targets})
    return result


def observe_original_primary_buttons(hwnd: int) -> dict:
    """Read-only UI Automation rooted at the existing strict WPF HWND witness."""
    require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
            "E07_UIA_NOT_WINDOWS_OR_BAD_HWND")
    ps = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if ($null -eq $root) { throw 'E07_UIA_NO_ROOT' }
$filter = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $filter)
$labels = [System.Collections.Generic.List[string]]::new()
for ($i=0; $i -lt $elements.Count; $i++) {
    $current = $elements.Item($i).Current
    $rect = $current.BoundingRectangle
    if ($current.IsEnabled -and -not $current.IsOffscreen -and
        $rect.Width -ge 20 -and $rect.Height -ge 12 -and
        -not [string]::IsNullOrWhiteSpace($current.Name)) {
        $labels.Add($current.Name)
    }
}
# Read-only structural witness: never promote Text/Custom/disabled/offscreen to Button PASS.
# Only known product button tokens and control types leave this Windows process.
$tree = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                      [System.Windows.Automation.Condition]::TrueCondition)
$scanCount = [Math]::Min([int]$tree.Count, 2048)
$targetTypes = [System.Collections.Generic.List[string]]::new()
for ($i=0; $i -lt $scanCount; $i++) {
    try {
        $node = $tree.Item($i).Current
        $name = $node.Name
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        $token = $name.Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim().ToUpperInvariant()
        if ($token -notin @('CHAT','INSTALL','MODELS','LEARN','REPORTS')) { continue }
        $kind = $node.ControlType.ProgrammaticName
        if ($kind -notin @('ControlType.Button','ControlType.Text','ControlType.Document',
                           'ControlType.Hyperlink','ControlType.Custom','ControlType.Group',
                           'ControlType.Pane','ControlType.Edit')) { $kind = 'Other' }
        $bounds = $node.BoundingRectangle
        $state = if (-not $node.IsEnabled) { 'DISABLED' }
                 elseif ($node.IsOffscreen) { 'OFFSCREEN' }
                 elseif ($bounds.Width -lt 20 -or $bounds.Height -lt 12) { 'TOO_SMALL' }
                 else { 'VISIBLE_ENABLED' }
        if ($targetTypes.Count -lt 64) { $targetTypes.Add("$token|$kind|$state") }
    } catch {
        # UIA may race on an exited WebView2 element; never elevate to proof.
    }
}
[pscustomobject]@{schema='NOX-E07-UIA-V1'; labels=@($labels.ToArray());
    treeCount=[int]$tree.Count; treeScanned=[int]$scanCount;
    targetTypes=@($targetTypes.ToArray())} |
    ConvertTo-Json -Compress -Depth 3
""".replace("__HWND__", str(hwnd))
    import base64
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", encoded],
                           cwd=os.environ["RUNNER_TEMP"], capture_output=True,
                           timeout=35, check=False, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired, KeyError):
        raise Hold("E07_UIA_EXECUTION_HOLD") from None
    require(p.returncode == 0 and len(p.stdout) <= 262144,
            "E07_UIA_PROCESS_HOLD")
    try:
        response = json.loads(p.stdout.strip())
    except (ValueError, UnicodeError):
        raise Hold("E07_UIA_BAD_JSON_HOLD") from None
    require(type(response) is dict and response.get("schema") == "NOX-E07-UIA-V1",
            "E07_UIA_BAD_SCHEMA_HOLD")
    return classify_primary_uia_evidence(response)


def original_wpf_hwnd(pid: int) -> int | None:
    """Original reviewed Win32 WPF class/PID/size witness; never generic HWND."""
    require(clean_file(_WPF_WITNESS_PATH), "E07_ORIGINAL_WPF_WITNESS_MISSING")
    spec = importlib.util.spec_from_file_location("_nox_e07_reviewed_wpf", _WPF_WITNESS_PATH)
    require(spec is not None and spec.loader is not None, "E07_ORIGINAL_WPF_WITNESS_UNLOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handle = module.find_visible_wpf_hwnd(pid)
    return handle if type(handle) is int and handle > 0 else None


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
            handle = original_wpf_hwnd(proc.pid)
            ready = (handle is not None and flags["NAV_OK"] and
                     flags["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"] and
                     not flags["NAV_FAIL"] and proc.poll() is None)
            if ready:
                if started is None:
                    started = time.monotonic()
                if time.monotonic() - started >= 8:
                    require(original_wpf_hwnd(proc.pid) == handle,
                            "E07_WPF_HWND_REPLACED_HOLD")
                    try:
                        buttons = observe_original_primary_buttons(handle)
                    except Hold as exc:
                        buttons = {"status": "HOLD", "error": str(exc),
                                   "actions_invoked": 0}
                    return {"gui_visible_hwnd": "PASS", "stable_seconds": 8,
                            "webview_navigation": "PASS", "shell_native_ipc": "PASS",
                            "independent_webview_log": "CURRENT_PROCESS_FRESH_NAV_AND_IPC",
                            "five_primary_buttons": buttons,
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


def native_store_stop_probe(backend: Path, scratch: Path) -> dict:
    """Independent installed SQLite-v4/empty-history/STOP ACK proof, not model inference.

    Separate native processes share only an isolated ephemeral data directory.
    An acknowledged idle STOP is NOT proof of interruption of a live stream.
    """
    require(clean_file(backend), "E07_NATIVE_STORE_EXE_MISSING")
    require(not scratch.exists() and not scratch.is_symlink(),
            "E07_NATIVE_STORE_SCRATCH_COLLISION")
    def request(route: str, nonce: str, run_id: str) -> dict:
        envelope = {"protocol": PROTOCOL, "requestId": nonce,
                    "runId": run_id, "route": route, "payload": {}}
        raw = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        execution = subprocess.run(
            [str(backend), "--native-stdio", "--run-id", run_id,
             "--data-dir", str(scratch)],
            input=struct.pack(">I", len(raw)) + raw,
            capture_output=True, timeout=105, cwd=str(backend.parent))
        require(execution.returncode == 0 and len(execution.stdout) >= 5,
                "E07_NATIVE_STORE_FRAME_HOLD")
        length = struct.unpack(">I", execution.stdout[:4])[0]
        require(1 <= length <= 1048576 and len(execution.stdout) == 4 + length,
                "E07_NATIVE_STORE_FRAME_HOLD")
        reply = json.loads(execution.stdout[4:].decode("utf-8", "strict"))
        require(type(reply) is dict and reply.get("status") == "OK" and
                all(reply.get(k) == envelope[k]
                    for k in ("protocol", "runId", "requestId")) and
                type(reply.get("result")) is dict,
                "E07_NATIVE_STORE_ACK_HOLD")
        return reply["result"]
    first = request("chat.history", "e7000000000000000000000000000001", "NOX-E07-STORE-A")
    second = request("chat.history", "e7000000000000000000000000000002", "NOX-E07-STORE-B")
    stop = request("chat.stop", "e7000000000000000000000000000003", "NOX-E07-STORE-C")
    require(type(first.get("messages")) is list and
            first["messages"] == second.get("messages") == [] and
            stop.get("stopRequested") is True,
            "E07_NATIVE_HISTORY_OR_STOP_HOLD")
    db = scratch / "helion.sqlite3"
    require(clean_file(db) and db.stat().st_size > 0,
            "E07_NATIVE_STORE_DB_MISSING")
    with closing(sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    require(version == 4 and integrity == "ok" and "core_chat_turns" in tables,
            "E07_NATIVE_STORE_SCHEMA_HOLD")
    return {"status": "PASS", "sqlite_user_version": 4,
            "sqlite_quick_check": "ok", "empty_history_restart": "PASS",
            "history_restart": "NOT_TESTED",
            "stop_ack": "PASS", "active_stream_stop": "NOT_TESTED",
            "real_model_inference": "NOT_TESTED"}

def verify_uninstall_no_loss(install: Path, stage: Path, previous: Path,
                             tracked: tuple[Path, ...], witness: Path,
                             expected: bytes) -> None:
    """Delete only manifest-owned payload; preserve independent unmanaged bytes."""
    def present(p: Path) -> bool:
        return p.exists() or p.is_symlink() or getattr(p, "is_junction", lambda: False)()
    require(not any(present(p) for p in tracked),
            "E07_NSIS_UNINSTALL_OWNED_RESIDUE_HOLD")
    require(clean_dir(install) and witness.parent == install and
            clean_file(witness) and witness.read_bytes() == expected,
            "E07_NSIS_UNINSTALL_UNOWNED_DATA_LOSS_HOLD")
    require(not any(present(p) for p in (stage, previous)),
            "E07_NSIS_UNINSTALL_STAGE_OR_PREVIOUS_RESIDUE_HOLD")


def verify_fresh_install_targets(local: Path, install: Path, stage: Path,
                                 previous: Path, saved: Path) -> None:
    """Reject reparse/alias install roots and recovery slots before NSIS /S.

    A dangling Windows junction can have exists()==False and is_symlink()==False.
    The base directory must also be trusted: otherwise a clean-looking slot can
    point outside the runner through LOCALAPPDATA/Programs.
    """
    require(clean_dir(local), "E07_LOCALAPPDATA_UNTRUSTED")
    base = local / "Programs"
    require(not base.is_symlink() and
            not getattr(base, "is_junction", lambda: False)() and
            (not base.exists() or clean_dir(base)),
            "E07_INSTALL_BASE_REPARSE_HOLD")
    require(all(slot.parent == base and not slot.exists() and
                not slot.is_symlink() and
                not getattr(slot, "is_junction", lambda: False)()
                for slot in (install, stage, previous, saved)),
            "E07_VM_NOT_FRESH_SKIP")


def lifecycle(setup: Path, result: dict) -> None:
    local = Path(os.environ["LOCALAPPDATA"])
    base = local / "Programs"
    install = base / "NOX HELION"
    stage = Path(str(install)+".__p01_stage")
    previous = Path(str(install)+".__p01_previous")
    saved = Path(str(install)+".__p01_rollback_saved")
    # Validate parent and all four slots BEFORE writing user data or running /S.
    verify_fresh_install_targets(local, install, stage, previous, saved)
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
    # Additive installed SQLite-v4/history/idle STOP proof; not active streaming or inference.
    try:
        result["checks"]["installed_native_store_stop"] = native_store_stop_probe(
            install/"Backend"/"NOX_HELION_PRIVATE_CANDIDATE.exe",
            Path(os.environ["RUNNER_TEMP"])/"nox-e07-native-store")
    except (Hold, sqlite3.Error, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        result["checks"]["installed_native_store_stop"] = {
            "status": "HOLD",
            "error": str(exc) if isinstance(exc, Hold) else
                     "E07_NATIVE_STORE_" + type(exc).__name__.upper() + "_HOLD"}
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
    # Unlisted bytes inside the install root must survive conservative uninstall.
    witness=install/"e07-independent-unmanaged-keep.txt"
    expected_witness=b"NOX_E07_UNMANAGED_INSTALL_DATA_PRESERVED\n"
    require(not witness.exists() and not witness.is_symlink(),
            "E07_UNMANAGED_WITNESS_COLLISION")
    witness.write_bytes(expected_witness)
    require(clean_file(witness), "E07_UNMANAGED_WITNESS_NONREGULAR")
    uninstaller=install/"Uninstall.exe"
    require(clean_file(uninstaller),"E07_UNINSTALL_EXE_MISSING")
    require(run([str(uninstaller),"/S"],limit=240)==0,"E07_NSIS_UNINSTALL_EXIT_HOLD")
    tracked=owned+(install/"payload.sha256.json",install/"nox-p01-owned.txt",uninstaller)
    deadline=time.monotonic()+180
    while any(p.exists() or p.is_symlink() for p in tracked) and time.monotonic()<deadline:
        time.sleep(0.3)
    verify_uninstall_no_loss(install,stage,previous,tracked,witness,expected_witness)
    require(user_marker.is_file() and user_marker.read_bytes()==signature,
            "E07_UNINSTALL_USER_DATA_LOSS")
    result["checks"]["uninstall"]={"status":"PASS", "owned_files_absent":len(owned),
                                    "userdata_preserved":True,
                                    "unmanaged_install_bytes_preserved":True,
                                    "install_root_retained_for_unmanaged_data":True,
                                    "stage_previous_absent":True}
    require(clean_dir(saved),"E07_BACKUP_POLICY_VIOLATED")
    result["checks"]["backup_retention"]={"status":"PASS","saved_rollback_slot_retained":True}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--artifact-dir",required=True,type=Path)
    p.add_argument("--artifact-kind",choices=("d02","original"),default="d02")
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    result={"schema":"NOX-EXPRESS-INDEPENDENT-E07-CANDIDATE-v1",
            "source_sha":ORIGINAL_E06_SOURCE if args.artifact_kind=="original" else SOURCE_SHA,
            "setup_sha256":ORIGINAL_E06_SETUP_SHA if args.artifact_kind=="original" else SETUP_SHA,
            "checks":{},"release_accepted":False,"independent_e07":"HOLD",
            "error":"NOT_RUN"}
    try:
        require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_HOST_NOT_AUTHORIZED")
        source = args.artifact_dir
        if args.artifact_kind == "original":
            setup=source/"NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe"
            result["checks"]["artifact"] = setup_lock_original(setup,source)
        else:
            setup=source/"e06"/"onehost-wow-diagnostic"/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
            receipt=source/"e06"/"onehost-wow-diagnostic"/"E07_BUILT_HANDOFF.json"
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
