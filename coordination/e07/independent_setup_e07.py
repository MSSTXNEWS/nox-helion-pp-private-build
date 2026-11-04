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

SOURCE_SHA = "834c443de53fd2c214750ed3c868133b70648c42"
SETUP_SHA = "4f78cd587e05bb1db49496a9a182225e8301bd5d84fee58a8022e9383a17c41e"
SETUP_SIZE = 169665062
RECEIPT_SCHEMA = "nox.express.onehost.same-sha.v1"
PROTOCOL = "NOX-P02-NATIVE-v1"

FINAL_VISUAL_SCHEMA = "NOX-E07-FINAL-VISUAL-v1"
FINAL_FUNCTION_SCHEMA = "NOX-E07-FINAL-FUNCTIONS-v1"
FINAL_FUNCTIONS = ("INSTALL", "MODELS", "LEARN", "SETTINGS")

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


E06_BUILD_ID = "NOX-V16-8a95972242fb9dc445f5fbe0"
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
FROZEN_E06_OWNED_COUNT = 1007

# Second immutable, physically built FULL-D02 candidate from Windows 41885544063.
# Only same-SHA evidence is admissible.  This is NOT a release receipt.
NEW_D02_SOURCE_SHA = "91a6c104c6412a63085352e224328d3c0ab3ff86"
NEW_D02_SETUP_SHA = "9884a33c3d6d924556602b68b0767ede7a3b2fe5432937b0cb29a49bea183a12"
NEW_D02_SETUP_SIZE = 169665842
NEW_D02_BUILD_ID = "NOX-V16-5d42f812b3ab0697d2da15ff"
NEW_D02_OWNED_COUNT = 1011

# Additional immutable FULL-D02 physical candidate. Source and installer identity
# from Windows E06 41895699906 receipts, recomputed over actual Setup.exe.
# Historical 91a6 and earlier candidate pins remain unchanged/non-promoted.
F842_D02_SOURCE_SHA = "f842297b79ec0bca0689d37af3ce7de7929fc450"
F842_D02_SETUP_SHA = "326f9ef5ac447a263f2af6aa920927f45b39498913cbf9d2dac72f24558575a1"
F842_D02_SETUP_SIZE = 169668831
F842_D02_BUILD_ID = "NOX-V16-3885169a467f2d1b53d57588"
F842_D02_OWNED_COUNT = 1011


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


def setup_lock(setup: Path, receipt: Path, *, candidate: str = "d02") -> dict:
    """Pin physical latest E06 Setup to three same-identity receipts, then verify bytes.

    Prior E06 same-VM lifecycle is NOT independent E07; lifecycle() must rerun.
    """
    require(candidate in ("d02", "d02-91a6", "d02-f842"), "E07_CANDIDATE_PIN_KIND_HOLD")
    if candidate == "d02-f842":
        expected_source, expected_setup_sha = F842_D02_SOURCE_SHA, F842_D02_SETUP_SHA
        expected_setup_size, expected_build_id = F842_D02_SETUP_SIZE, F842_D02_BUILD_ID
        expected_owned_count = F842_D02_OWNED_COUNT
    elif candidate == "d02-91a6":
        expected_source, expected_setup_sha = NEW_D02_SOURCE_SHA, NEW_D02_SETUP_SHA
        expected_setup_size, expected_build_id = NEW_D02_SETUP_SIZE, NEW_D02_BUILD_ID
        expected_owned_count = NEW_D02_OWNED_COUNT
    else:
        expected_source, expected_setup_sha = SOURCE_SHA, SETUP_SHA
        expected_setup_size, expected_build_id = SETUP_SIZE, E06_BUILD_ID
        expected_owned_count = FROZEN_E06_OWNED_COUNT
    require(clean_file(setup) and clean_file(receipt), "E07_SOURCE_ARTIFACT_NOT_REGULAR")
    require(setup.parent == receipt.parent and receipt.name == "E07_BUILT_HANDOFF.json",
            "E07_E06_HANDOFF_PATH_HOLD")
    handoff = _read_locked_e06_json(receipt)
    diagnostic = _read_locked_e06_json(receipt.parent/"ONEHOST_DIAGNOSTIC_RECEIPT.json")
    smoke = _read_locked_e06_json(receipt.parent/"T06_INSTALLED_SMOKE.json")
    require(handoff.get("schema") == "NOX_V16_E07_IMMUTABLE_HANDOFF_V1" and
            handoff.get("source_commit_sha1") == expected_source and
            handoff.get("build_id") == expected_build_id and
            handoff.get("phase") == "BUILT" and
            handoff.get("original_zip_sha256") == ORIGINAL_ZIP_SHA and
            handoff.get("source_files") == 729 and
            handoff.get("source_receipts_729_parity_verified") is True and
            handoff.get("setup_sha256") == expected_setup_sha and
            type(handoff.get("independent_e07_cases_accepted")) is int and
            handoff["independent_e07_cases_accepted"] == 0 and
            handoff.get("release_accepted") is False and
            handoff.get("status") == "PENDING_E07_INDEPENDENT_SAME_SHA_QA",
            "E07_E06_HANDOFF_IDENTITY_HOLD")
    require(diagnostic.get("schema") == "NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1" and
            diagnostic.get("source_commit_sha1") == expected_source and
            diagnostic.get("installer_sha256") == expected_setup_sha and
            type(diagnostic.get("installer_bytes")) is int and
            diagnostic["installer_bytes"] == expected_setup_size and
            diagnostic.get("release_accepted") is False and
            diagnostic.get("status") == "WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED",
            "E07_E06_DIAGNOSTIC_IDENTITY_HOLD")
    stages = smoke.get("installer_lifecycle")
    require(smoke.get("schema") == "NOX-T06-INSTALLED-SMOKE-v1" and
            smoke.get("phase") == "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07" and
            smoke.get("build_id") == expected_build_id and
            smoke.get("setup_sha256") == expected_setup_sha and
            smoke.get("release_accepted") is False and
            smoke.get("e07_independent_acceptance") == "NOT_RUN" and
            samevm_lifecycle_verified(stages, expected_owned_files=expected_owned_count),
            "E07_E06_SAMEVM_RECEIPT_HOLD")
    require(clean_dir(setup.parent), "E07_SETUP_PARENT_REPARSE_HOLD")
    locked_sha, header = installed_file_sha_locked(
        setup, setup.parent.resolve(strict=True), expected_setup_size, expected_setup_sha,
        return_pe_header=True)
    require(locked_sha == expected_setup_sha, "E07_SETUP_SHA_HOLD")
    require(len(header) >= 64 and header[:2] == b"MZ", "E07_SETUP_WINDOWS_PE_HOLD")
    offset = struct.unpack_from("<I", header, 0x3c)[0]
    require(offset <= len(header)-6 and header[offset:offset+4] == b"PE\0\0",
            "E07_SETUP_WINDOWS_PE_HOLD")
    return {"source_sha":expected_source,"setup_sha256":expected_setup_sha,
            "setup_bytes":expected_setup_size,"pe_machine":hex(struct.unpack_from("<H",header,offset+4)[0]),
            "build_id":expected_build_id,"e06_samevm_pass_not_e07":True}



# Frozen ORIGINAL OneHost E06 Setup from run 41797861187 (not D02).
# All three real producer receipts and binary/source SHA must agree.
ORIGINAL_E06_SOURCE = "fe21790af418c8c1083946595811b67c9c03c49d"
ORIGINAL_E06_SETUP_SHA = "1b78fba3fa158673814b31f211063022fd2bff0ae7ff25f14ba3db2a47c484c2"
ORIGINAL_E06_SETUP_BYTES = 87333614
ORIGINAL_E06_SOURCE_ZIP_SHA = "80e46b37260680eaa434211ebbe98d8498c8481e9b384e8895e26c810b995106"
ORIGINAL_E06_OWNED_FILES = 485
ORIGINAL_E06_PUBLISHED_HOME_SHA = "37c7952d98e820b22ea59c72c967bc4f7ecf01da013b3269b53e9f698062586e"

def setup_lock_original(setup: Path, base: Path, *, frozen: str = "legacy") -> dict:
    """Bind each immutable original E06 candidate to its own physical receipts."""
    require(frozen == "30a" or frozen in ("legacy", "e888"), "E07_ORIGINAL_PIN_KIND_HOLD")
    if frozen == "e888":
        # Physical source and ZIP independently cross-checked by a different worker,
        # artifact 13309335494 from producer Windows E06 41803143292.
        expected_source = "e888941626191c17d19d372889b1f96842c15e1b"
        expected_setup_sha = "96ff9b47ca12a21017374e527786eda8b8fbf2b0e62cc6cfea1f59182cc8e61b"
        expected_setup_bytes = 87335268
        expected_source_zip_sha = "1af961a3937d930a5f4684dd1cc88890b81b1e1ec61abfcfa3e72b250ca12683"
        expected_owned_files = 485
        expected_home_bytes = 99768
        expected_home_sha = "5661491ddf07b3f5fa7c8097ff64838209057bee6a0bec8ed867b8c8553a40d0"
    elif frozen == "30a":
        # Frozen immutable physical source/Setup receipts from independent
        # Windows producer #41867828741 / artifact #13343191933.
        # This is still a DIAGNOSTIC candidate: no copied E07/Qwen/UIA PASS.
        expected_source = "30a4f7c43649e3c3d66d0d46ec370b2105a69faa"
        expected_setup_sha = "ceb4aab254a6a61b16b25a225ba443149bf1260c3ac410f0c00047842ab9c48c"
        expected_setup_bytes = 87334495
        expected_source_zip_sha = "07957aabe4d03cb0a63e3365bbef67f90ddf46a197b1cf0e91dceb943541eec9"
        expected_owned_files = 485
        expected_home_bytes = 105949
        expected_home_sha = "32b24bb6d7cc758ef18397d32f11c704deacce38fe5e52dbde31ef2fb469280e"
    else:
        expected_source = ORIGINAL_E06_SOURCE
        expected_setup_sha = ORIGINAL_E06_SETUP_SHA
        expected_setup_bytes = ORIGINAL_E06_SETUP_BYTES
        expected_source_zip_sha = ORIGINAL_E06_SOURCE_ZIP_SHA
        expected_owned_files = ORIGINAL_E06_OWNED_FILES
        expected_home_bytes = 99762
        expected_home_sha = ORIGINAL_E06_PUBLISHED_HOME_SHA
    require(clean_dir(base) and setup.parent == base and
            setup.name == "NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe",
            "E07_ORIGINAL_CANDIDATE_PATH_HOLD")
    build = _read_locked_e06_json(base/"BUILD_RECEIPT.json")
    candidate = _read_locked_e06_json(base/"ONEHOST_CANDIDATE_RECEIPT.json")
    smoke = _read_locked_e06_json(base/"T06_INSTALLED_SMOKE.json")
    require(build.get("schema")==RECEIPT_SCHEMA and
            build.get("source_commit")==expected_source and
            build.get("physical_setup_built") is True and
            build.get("setup_sha256")==expected_setup_sha and
            type(build.get("setup_bytes")) is int and
            build["setup_bytes"]==expected_setup_bytes and
            build.get("build_outcome")=="success" and
            build.get("classification")=="DIAGNOSTIC_CANDIDATE_NOT_RELEASE" and
            build.get("release_accepted") is False and
            build.get("independent_e07")=="NOT_RUN",
            "E07_ORIGINAL_BUILD_RECEIPT_HOLD")
    require(candidate.get("schema")=="NOX-E06-ONEHOST-CANDIDATE-v1" and
            candidate.get("source_git_sha")==expected_source and
            candidate.get("setup_sha256")==expected_setup_sha and
            type(candidate.get("setup_bytes")) is int and
            candidate["setup_bytes"]==expected_setup_bytes and
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
            home["published_home_bytes"]==expected_home_bytes and
            type(home.get("published_home_sha256")) is str and
            home["published_home_sha256"]==expected_home_sha,
            "E07_ORIGINAL_HOME_RECEIPT_HOLD")
    require(smoke.get("schema")=="NOX-T06-INSTALLED-SMOKE-v1" and
            smoke.get("phase")=="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07" and
            smoke.get("environment")=="GITHUB_WINDOWS_EPHEMERAL_BRIDGE_NOT_E07" and
            smoke.get("setup_sha256")==expected_setup_sha and
            smoke.get("installed_wpf_sha256")==candidate.get("wpf_sha256") and
            smoke.get("installed_backend_sha256")==candidate.get("backend_sha256") and
            smoke.get("manifest_sha256")==candidate.get("manifest_sha256") and
            smoke.get("e07_independent_acceptance")=="NOT_RUN" and
            smoke.get("release_accepted") is False and
            type(smoke.get("manifest_files_checked")) is int and
            smoke["manifest_files_checked"]==expected_owned_files and
            samevm_lifecycle_verified(smoke.get("installer_lifecycle"),
                expected_owned_files=expected_owned_files),
            "E07_ORIGINAL_SAMEVM_RECEIPT_HOLD")
    source=base/("NOX_HELION_EXPRESS_SOURCE_"+expected_source+".zip")
    require(clean_file(source) and sha256(source)==expected_source_zip_sha,
            "E07_ORIGINAL_SOURCE_ZIP_SHA_HOLD")
    require(clean_file(setup) and setup.stat().st_size==expected_setup_bytes,
            "E07_ORIGINAL_SETUP_BYTES_HOLD")
    checked,header=installed_file_sha_locked(setup,base.resolve(strict=True),
        expected_setup_bytes,expected_setup_sha,return_pe_header=True)
    require(checked==expected_setup_sha and len(header)>=64 and
            header[:2]==b"MZ", "E07_ORIGINAL_SETUP_PE_HOLD")
    offset=struct.unpack_from("<I",header,0x3c)[0]
    require(offset<=len(header)-6 and header[offset:offset+4]==bytes.fromhex("50450000"),
            "E07_ORIGINAL_SETUP_PE_HOLD")
    return {"source_sha":expected_source,
            "setup_sha256":expected_setup_sha,
            "setup_bytes":expected_setup_bytes,
            "source_zip_sha256":expected_source_zip_sha,
            "build_id":"NOT_PROVIDED_IN_E06_RECEIPT",
            "e06_samevm_pass_not_e07":True,
            "owned_count_source_pinned":expected_owned_files,
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
    # This is a separate E07 probe from native_store_stop_probe. Fail closed
    # BEFORE the installed OneHost can create SQLite in an untrusted --data-dir.
    # A dangling Windows directory junction may have exists() == False.
    runner_temp = os.environ.get("RUNNER_TEMP")
    require(type(runner_temp) is str and bool(runner_temp.strip()) and
            scratch.is_absolute() and
            scratch == Path(runner_temp) / "nox-e07-native-data" and
            clean_dir(scratch.parent) and
            all(not parent.is_symlink() and
                not getattr(parent, "is_junction", lambda: False)()
                for parent in scratch.parents) and
            not scratch.exists() and not scratch.is_symlink() and
            not getattr(scratch, "is_junction", lambda: False)(),
            "E07_NATIVE_INVENTORY_SCRATCH_COLLISION")
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


_UIA_MAIN_BUTTONS = ("CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS")

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
                r"(CHAT|INSTALL|MODELS|LEARN|SETTINGS)\|"
                r"(ControlType\.(Button|Text|Document|Hyperlink|Custom|Group|Pane|Edit)|Other)\|"
                r"(VISIBLE_ENABLED|OFFSCREEN|DISABLED|TOO_SMALL)", item)
                for item in targets), "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD")
    require(len(targets) <= scanned, "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD")
    result = classify_primary_button_names(response.get("labels"))
    # Chromium UIA providers can enumerate a real visible Button in unfiltered
    # descendants even when the separate Button property-filter returns [].
    # These are the SAME HWND-rooted physical UIA elements, NOT text/Custom or
    # an inferred click. Only the exact visible+enabled Button role is admitted.
    role_witnesses = [entry.split("|", 1)[0] for entry in targets
                      if entry.endswith("|ControlType.Button|VISIBLE_ENABLED")]
    # Label strings alone are not correlated to a physical Button-role node.
    # Count exact role-qualified nodes: duplicates make UI actions ambiguous.
    # Unmatched labels remain diagnostic evidence and NEVER a release PASS.
    found = set(role_witnesses)
    duplicates = [name for name in _UIA_MAIN_BUTTONS
                  if role_witnesses.count(name) > 1]
    result.update({"status": "PASS" if len(found) == len(_UIA_MAIN_BUTTONS)
                    and not duplicates else "HOLD",
                   "buttons_present": [v for v in _UIA_MAIN_BUTTONS if v in found],
                   "buttons_missing": [v for v in _UIA_MAIN_BUTTONS if v not in found],
                   "buttons_duplicate": duplicates,
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
        if ($token -notin @('CHAT','INSTALL','MODELS','LEARN','SETTINGS')) { continue }
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



def classify_chat_invoke_witness(response: dict) -> dict:
    """Only a NEW visible CHAT heading after a real UIA click proves navigation.

    Presence of the original button or a live HWND does not prove a route.
    A preexisting heading is not transition evidence. Model/visual E07 stay HOLD.
    """
    require(type(response) is dict and
            set(response) == {"schema", "action", "invoked", "sameHwndAlive",
                              "beforeChatHeading", "afterChatHeading"} and
            response.get("schema") == "NOX-E07-CHAT-INPUT-v2" and
            response.get("action") == "CHAT" and response.get("invoked") is True and
            response.get("sameHwndAlive") is True and
            type(response.get("beforeChatHeading")) is bool and
            type(response.get("afterChatHeading")) is bool,
            "E07_CHAT_ACTION_UNTRUSTED_HOLD")
    changed = response["beforeChatHeading"] is False and response["afterChatHeading"] is True
    return {"status": "OBSERVED", "action": "CHAT", "actions_invoked": 1,
            "method": "NATIVE_UIA_INVOKEPATTERN",
            "navigation_verified": "PASS" if changed else "NOT_TESTED",
            "navigation_proof": "NEW_VISIBLE_UIA_CHAT_HEADING" if changed else "NONE",
            "visual_e07": "HOLD", "model_inference": "NOT_TESTED"}


def observe_chat_input(hwnd: int) -> dict:
    """Input-only witness against installed WPF HWND; no privileged button invoked."""
    require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
            "E07_CHAT_ACTION_HOST_HOLD")
    ps = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$hwnd=[IntPtr]__HWND__
$root=[System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if($null -eq $root){throw 'NO_ROOT'}
$tree=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
if($tree.Count -gt 2048){throw 'TREE_UNBOUNDED'}
$matching=[System.Collections.Generic.List[System.Windows.Automation.AutomationElement]]::new()
for($i=0;$i -lt $tree.Count;$i++){
  $el=$tree.Item($i)
  $v=$el.Current
  if($v.ControlType -ne [System.Windows.Automation.ControlType]::Button){continue}
  $name=($v.Name+'').Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim().ToUpperInvariant()
  if($name -ne 'CHAT'){continue}
  $rect=$v.BoundingRectangle
  if($v.IsEnabled -and -not $v.IsOffscreen -and $rect.Width -ge 20 -and $rect.Height -ge 12){$matching.Add($el)}
}
if($matching.Count -ne 1){throw 'CHAT_NOT_UNIQUE'}
# Read the ORIGINAL installed WebView2 accessibility tree, not HTML from repository.
# Require a freshly appearing visible heading, not a button click or static label.
function Test-ChatHeading($root){
  $nodes=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  if($nodes.Count -gt 2048){throw 'CHAT_TREE_UNBOUNDED'}
  for($j=0;$j -lt $nodes.Count;$j++){
    $v=$nodes.Item($j).Current
    if($v.ControlType -ne [System.Windows.Automation.ControlType]::Text){continue}
    if(($v.Name+'').Trim() -ne 'ЖИВОЙ ЧАТ'){continue}
    $rect=$v.BoundingRectangle
    if(-not $v.IsOffscreen -and $rect.Width -ge 20 -and $rect.Height -ge 12){return $true}
  }
  return $false
}
$beforeHeading=Test-ChatHeading $root
$pattern=$matching.Item(0).GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
if($null -eq $pattern){throw 'NO_INVOKEPATTERN'}
$pattern.Invoke()
$afterHeading=$false
$deadline=[DateTime]::UtcNow.AddSeconds(8)
do {
  Start-Sleep -Milliseconds 180
  $fresh=[System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
  if($null -eq $fresh){break}
  $afterHeading=Test-ChatHeading $fresh
} until($afterHeading -or [DateTime]::UtcNow -ge $deadline)
$alive=$null -ne [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
[pscustomobject]@{schema='NOX-E07-CHAT-INPUT-v2';action='CHAT';invoked=$true;sameHwndAlive=$alive;beforeChatHeading=$beforeHeading;afterChatHeading=$afterHeading}|ConvertTo-Json -Compress
""".replace("__HWND__", str(hwnd))
    import base64
    encoded=base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    try:
        p=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
                          "-EncodedCommand",encoded],
                         cwd=os.environ["RUNNER_TEMP"], capture_output=True,
                         timeout=30, check=False, encoding="utf-8", errors="replace")
    except (OSError,subprocess.TimeoutExpired,KeyError):
        raise Hold("E07_CHAT_ACTION_EXECUTION_HOLD") from None
    require(p.returncode == 0 and 0 < len(p.stdout) <= 2048,
            "E07_CHAT_ACTION_PROCESS_HOLD")
    try:
        witness=json.loads(p.stdout.strip())
    except (ValueError,UnicodeError):
        raise Hold("E07_CHAT_ACTION_JSON_HOLD") from None
    return classify_chat_invoke_witness(witness)



def classify_readonly_primary_navigation_witness(response: dict) -> dict:
    """Physical route to a visible original screen and focused real control; not install/training execution."""
    expected = ("INSTALL", "MODELS", "LEARN", "SETTINGS")
    require(type(response) is dict and set(response) == {"schema", "actions"} and
            response["schema"] in ("NOX-E07-PRIMARY-NAV-v2", "NOX-E07-PRIMARY-NAV-v3") and
            type(response["actions"]) is list and len(response["actions"]) == 4,
            "E07_PRIMARY_NAV_SCHEMA_HOLD")
    checks = {}
    extended = response["schema"] == "NOX-E07-PRIMARY-NAV-v3"
    for index, raw in enumerate(response["actions"]):
        require(type(raw) is dict and
                set(raw) == ({"action", "invoked", "sameHwndAlive",
                              "beforeDestination", "afterDestination"} |
                             ({"beforeHeadingVisible", "afterHeadingVisible",
                               "beforeFocusedControls", "afterFocusedControls"}
                              if extended else set())) and
                type(raw["action"]) is str and raw["action"] == expected[index] and
                type(raw["invoked"]) is bool and
                type(raw["sameHwndAlive"]) is bool and
                type(raw["beforeDestination"]) is bool and
                type(raw["afterDestination"]) is bool,
                "E07_PRIMARY_NAV_UNTRUSTED_HOLD")
        if extended:
            require(type(raw["beforeHeadingVisible"]) is bool and
                    type(raw["afterHeadingVisible"]) is bool and
                    type(raw["beforeFocusedControls"]) is int and
                    type(raw["afterFocusedControls"]) is int and
                    0 <= raw["beforeFocusedControls"] <= 2 and
                    0 <= raw["afterFocusedControls"] <= 2 and
                    raw["beforeDestination"] is (raw["beforeHeadingVisible"] and
                                                 raw["beforeFocusedControls"] == 1) and
                    raw["afterDestination"] is (raw["afterHeadingVisible"] and
                                                raw["afterFocusedControls"] == 1),
                    "E07_PRIMARY_NAV_COMPONENT_INCONSISTENT_HOLD")
        changed = (raw["invoked"] is True and raw["sameHwndAlive"] is True and
                   raw["beforeDestination"] is False and raw["afterDestination"] is True)
        checks[raw["action"]] = {
            "button_actuated": "OBSERVED" if raw["invoked"] else "HOLD",
            "navigation_verified": "PASS" if changed else "NOT_TESTED",
            "function_verified": "NOT_TESTED"}
        if extended:
            # Bounded role/visibility diagnostics, no text, user data or fake PASS.
            checks[raw["action"]]["destination_components"] = {
                "before_heading_visible": raw["beforeHeadingVisible"],
                "after_heading_visible": raw["afterHeadingVisible"],
                "before_focused_controls": raw["beforeFocusedControls"],
                "after_focused_controls": raw["afterFocusedControls"],
            }
    complete = all(value["navigation_verified"] == "PASS" for value in checks.values())
    return {"status": "OBSERVED" if complete else "HOLD",
            "actions_invoked": sum(value["button_actuated"] == "OBSERVED"
                                   for value in checks.values()),
            "navigation_verified": "PASS" if complete else "HOLD",
            "per_action": checks, "visual_e07": "HOLD",
            "model_inference": "NOT_TESTED", "release_accepted": False}


def observe_readonly_primary_navigation(hwnd: int) -> dict:
    """Invoke four source-locked original HOME routes on installed Windows UI.

    Original menu.js: INSTALL/system and LEARN/evolution are non-mutating
    informational panels; MODELS/catalog and SETTINGS/settings are read-only
    OneHost routes. No button inside a panel, install, pull or training is invoked.
    """
    require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
            "E07_PRIMARY_NAV_HOST_HOLD")
    ps = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$handle=[IntPtr]__HWND__
$destinations=@{
 INSTALL=@{title='';control='УСТАНОВИТЬ NOX'}
 MODELS=@{title='NOX · CONTROL CENTER';control='МОДЕЛИ И КОМПОНЕНТЫ'}
 LEARN=@{title='NOX · CONTROL CENTER';control='ЗАПУСТИТЬ ОБУЧЕНИЕ'}
 SETTINGS=@{title='СИСТЕМА';control='← НАЗАД В МЕНЮ'}
}
function Get-SameRoot {
  $v=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
  if($null -eq $v){throw 'E07_PRIMARY_NAV_HWND_LOST'}
  return $v
}
# A route must expose the ORIGINAL visible screen AND keyboard-focus its
# ORIGINAL destination control. Distinct buttons on the same CONTROL CENTER
# screen cannot be verified by repeated headings alone.
function Test-RealDestination($hostRoot,[string]$name) {
  $spec=$destinations[$name]
  $tree=$hostRoot.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                         [System.Windows.Automation.Condition]::TrueCondition)
  if($tree.Count -gt 2048){throw 'E07_PRIMARY_NAV_TREE_LIMIT'}
  # Original R11 INSTALL is a GLOBAL hostcontrols button, not a screen.
  # Its unique visible keyboard-focused native control IS the destination.
  # No installation is invoked and no install-function PASS can be inferred.
  $headingVisible=($name -eq 'INSTALL')
  $focusedControls=0
  for($k=0;$k -lt $tree.Count;$k++){
    try{
      $v=$tree.Item($k).Current
      $rect=$v.BoundingRectangle
      # Focus may scroll the original page, taking its genuine heading above
      # the viewport. The original title still has to exist in this same HWND
      # accessibility tree, while the destination CONTROL must remain onscreen.
      if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
         ($v.Name+'').Trim() -ceq $spec.title){$headingVisible=$true}
      if($v.IsOffscreen -or $rect.Width -lt 20 -or $rect.Height -lt 12){continue}
      if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
         ($v.Name+'').Trim() -ceq $spec.control -and $v.IsEnabled -and
         $v.HasKeyboardFocus){$focusedControls++}
    }catch{}
  }
  return [pscustomobject]@{confirmed=($headingVisible -and $focusedControls -eq 1);
                          headingVisible=$headingVisible;
                          focusedControls=[Math]::Min($focusedControls,2)}
}
$actions=@()
foreach($name in @('INSTALL','MODELS','LEARN','SETTINGS')){
  $root=Get-SameRoot
  $nodes=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                       [System.Windows.Automation.Condition]::TrueCondition)
  if($nodes.Count -gt 2048){throw 'E07_PRIMARY_NAV_TREE_LIMIT'}
  $found=New-Object System.Collections.ArrayList
  for($i=0;$i -lt $nodes.Count;$i++){
    try {
      $el=$nodes.Item($i);$v=$el.Current
      if($v.ControlType -ne [System.Windows.Automation.ControlType]::Button){continue}
      $token=($v.Name+'').Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim().ToUpperInvariant()
      if($token -ne $name){continue}
      $rect=$v.BoundingRectangle
      if($v.IsEnabled -and -not $v.IsOffscreen -and $rect.Width -ge 20 -and $rect.Height -ge 12){
        $null=$found.Add($el)
      }
    }catch{}
  }
  if($found.Count -ne 1){throw 'E07_PRIMARY_NAV_BUTTON_NOT_UNIQUE'}
  $beforeState=Test-RealDestination $root $name
  $before=$beforeState.confirmed
  $pattern=$found.Item(0).GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  if($null -eq $pattern){throw 'E07_PRIMARY_NAV_INVOKEPATTERN_MISSING'}
  $pattern.Invoke()
  $after=$false
  $afterState=$beforeState
  for($retry=0;$retry -lt 28;$retry++){
    Start-Sleep -Milliseconds 180
    $fresh=Get-SameRoot
    $afterState=Test-RealDestination $fresh $name
    if($afterState.confirmed){$after=$true;break}
  }
  $alive=$null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle)
  $actions+=([pscustomobject]@{action=$name;invoked=$true;sameHwndAlive=$alive;
                              beforeDestination=$before;afterDestination=$after;
                              beforeHeadingVisible=$beforeState.headingVisible;
                              afterHeadingVisible=$afterState.headingVisible;
                              beforeFocusedControls=$beforeState.focusedControls;
                              afterFocusedControls=$afterState.focusedControls})
}
[pscustomobject]@{schema='NOX-E07-PRIMARY-NAV-v3';actions=@($actions)} |
  ConvertTo-Json -Compress -Depth 5
""".replace("__HWND__", str(hwnd))
    import base64
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", encoded],
                           capture_output=True, text=True, timeout=100,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        raise Hold("E07_PRIMARY_NAV_EXECUTION_HOLD") from None
    require(p.returncode == 0 and 0 < len(p.stdout) <= 8192,
            "E07_PRIMARY_NAV_PROCESS_HOLD")
    try:
        witness = json.loads(p.stdout.strip())
    except (ValueError, UnicodeError):
        raise Hold("E07_PRIMARY_NAV_JSON_HOLD") from None
    return classify_readonly_primary_navigation_witness(witness)


def original_wpf_hwnd(pid: int) -> int | None:
    """Original reviewed Win32 WPF class/PID/size witness; never generic HWND."""
    require(clean_file(_WPF_WITNESS_PATH), "E07_ORIGINAL_WPF_WITNESS_MISSING")
    spec = importlib.util.spec_from_file_location("_nox_e07_reviewed_wpf", _WPF_WITNESS_PATH)
    require(spec is not None and spec.loader is not None, "E07_ORIGINAL_WPF_WITNESS_UNLOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handle = module.find_visible_wpf_hwnd(pid)
    return handle if type(handle) is int and handle > 0 else None


def gui_hwnd(shell: Path, local: Path, *, safe_nav: bool = False,
             final_probe=None) -> dict:
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
                    # Actuate only existing CHAT, keep remaining 4 untouched.
                    action = {"status": "HOLD", "actions_invoked": 0,
                              "navigation_verified": "NOT_TESTED", "visual_e07": "HOLD"}
                    if buttons.get("status") == "PASS":
                        try:
                            action = observe_chat_input(handle)
                        except Hold as exc:
                            action["error"] = str(exc)
                    nav = {"status":"HOLD","reason":"NOT_TESTED_UNPINNED_SOURCE",
                           "navigation_verified":"NOT_TESTED","visual_e07":"HOLD"}
                    if safe_nav and buttons.get("status") == "PASS":
                        try:
                            nav = observe_readonly_primary_navigation(handle)
                        except Hold as exc:
                            nav = {"status":"HOLD","error":str(exc),
                                   "navigation_verified":"NOT_TESTED","visual_e07":"HOLD"}
                    # The original WPF HWND is alive HERE. Running the physical
                    # visual/function witness after this function returns would
                    # use a terminated shell and cannot establish same-Setup proof.
                    final_witness = {"status":"HOLD", "error":"E07_FINAL_PHYSICAL_NOT_RUN"}
                    if final_probe is not None:
                        try:
                            final_witness = final_probe(handle)
                        except (Hold, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                            final_witness = {"status":"HOLD", "error":str(exc) if isinstance(exc, Hold)
                                             else "E07_FINAL_"+type(exc).__name__.upper()+"_HOLD"}
                        except Exception as exc:
                            final_witness = {"status":"HOLD", "error":"E07_FINAL_UNEXPECTED_"+type(exc).__name__.upper()+"_HOLD"}
                    return {"gui_visible_hwnd": "PASS", "stable_seconds": 8,
                            "webview_navigation": "PASS", "shell_native_ipc": "PASS",
                            "independent_webview_log": "CURRENT_PROCESS_FRESH_NAV_AND_IPC",
                            "five_primary_buttons": buttons,
                            "ui_chat_action_probe": action,
                            "ui_safe_primary_navigation": nav,
                            "visual_e07": "HOLD", "final_physical_witness":final_witness}
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
    runner_temp = os.environ.get("RUNNER_TEMP")
    # A missing-path Windows junction may redirect the native SQLite probe
    # outside the isolated runner while exists() is still false.
    require(type(runner_temp) is str and bool(runner_temp.strip()) and
            scratch.is_absolute() and
            scratch == Path(runner_temp) / "nox-e07-native-store" and
            clean_dir(scratch.parent) and
            all(not parent.is_symlink() and
                not getattr(parent, "is_junction", lambda: False)()
                for parent in scratch.parents) and
            not scratch.exists() and not scratch.is_symlink() and
            not getattr(scratch, "is_junction", lambda: False)(),
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


def _bounded_live_probe_failure(path: Path, *, expected_schema: str,
                                default_code: str) -> str:
    """Retain a child's *real* first HOLD without copying logs, paths or claims.

    Existing Windows E07 used to collapse every failed Qwen/STOP child into a
    generic code, losing the OCI/ownership reason after lifecycle cleanup.
    Never turn a child receipt into PASS, and never expose arbitrary text.
    """
    try:
        if not clean_file(path) or path.stat().st_size > 65536:
            return default_code
        evidence = _read_locked_e06_json(path)
        if (evidence.get("schema") != expected_schema or
                evidence.get("release_accepted") is not False or
                evidence.get("independent_e07") != "HOLD"):
            return default_code
        reason = evidence.get("first_unmet_gate")
        if type(reason) is not str or re.fullmatch(
                r"[A-Z][A-Z0-9_]{3,110}", reason) is None:
            return default_code
        return default_code + ":" + reason
    except (Hold, OSError, UnicodeError, ValueError):
        return default_code


def installed_live_qwen_gates(backend: Path) -> dict:
    """Re-use approved physical probes on the SAME installed backend before NSIS uninstall.

    No new provider, fake inference, second DB, or release promotion. Both
    receipts originate in the isolated Windows E07 VM and fail closed.
    """
    require(clean_file(backend), "E07_QWEN_INSTALLED_BACKEND_MISSING_HOLD")
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    proof = runner_temp / "nox-e07-express-live-proof"
    require(clean_dir(runner_temp) and not proof.exists() and
            not proof.is_symlink() and
            not getattr(proof, "is_junction", lambda: False)(),
            "E07_QWEN_PROOF_SCRATCH_COLLISION_HOLD")
    proof.mkdir()
    repository = Path(os.environ["GITHUB_WORKSPACE"])
    scripts = repository / "coordination" / "e07"
    qwen_script = scripts / "probe_installed_qwen.py"
    stop_script = scripts / "probe_native_active_stop.py"
    require(all(clean_file(p) for p in (qwen_script, stop_script)),
            "E07_REVIEWED_NATIVE_PROBE_MISSING_HOLD")
    qwen_out = proof / "QWEN_INSTALLED.json"
    stop_out = proof / "ACTIVE_STOP.json"
    commands = (
        ([sys.executable, "-B", str(qwen_script), "--backend", str(backend),
          "--out", str(qwen_out)], "E07_INSTALLED_QWEN_LIVE_SQLITE_HOLD"),
        ([sys.executable, "-B", str(stop_script), "--backend", str(backend),
          "--data-dir", str(proof / "active-stop-native"),
          "--model", "qwen2.5-coder:1.5b", "--out", str(stop_out)],
         "E07_INSTALLED_ACTIVE_STREAM_STOP_HOLD"),
    )
    for command, failure in commands:
        if command is commands[1][0]:
            (proof / "active-stop-native").mkdir()
        completed = subprocess.run(command, cwd=str(repository), check=False,
                                   capture_output=True, timeout=480)
        if completed.returncode != 0:
            # Never copy subprocess stdout/stderr or human text into receipts.
            # Read only its fresh, schema-bound, release-HOLD JSON, and only a
            # bounded machine reason. Unknown/malformed evidence stays HOLD.
            detail = _bounded_live_probe_failure(
                qwen_out if command is commands[0][0] else stop_out,
                expected_schema=("nox.installed.qwen.e07-diagnostic.v1"
                                 if command is commands[0][0]
                                 else "nox.native.active-stop.physical.v1"),
                default_code=failure)
            raise Hold(detail)
    qwen = _read_locked_e06_json(qwen_out)
    stop = _read_locked_e06_json(stop_out)
    require(qwen.get("installed_backend_sha256") == sha256(backend) and
            qwen.get("installed_native") == "LIVE_NONEMPTY_RESPONSE_VERIFIED" and
            qwen.get("native_history_restart") == "PASS" and
            type(qwen.get("sqlite_history_rows_after_restart")) is int and
            qwen["sqlite_history_rows_after_restart"] >= 2 and
            qwen.get("independent_weight_sha_verified") is True and
            qwen.get("release_accepted") is False,
            "E07_LIVE_QWEN_WEIGHT_CHAT_SQLITE_EVIDENCE_HOLD")
    require(stop.get("native_active_stop") == "PASS" and
            stop.get("interrupted_chat_terminal") == "NATIVE_CHAT_STOP" and
            stop.get("native_stop_ack") == "PASS" and
            stop.get("release_accepted") is False,
            "E07_LIVE_ACTIVE_STOP_EVIDENCE_HOLD")
    return {"status": "PASS", "model": "qwen2.5-coder:1.5b",
            "installed_backend_sha256": qwen["installed_backend_sha256"],
            "verified_oci_blobs": qwen.get("verified_model_oci_blobs"),
            "nonempty_native_chat": "PASS", "history_after_restart": "PASS",
            "history_rows": qwen["sqlite_history_rows_after_restart"],
            "active_mid_stream_stop": "PASS", "stop_ack": "PASS",
            "release_accepted": False}



def evaluate_final_acceptance(visual: object, functions: object, *,
                              source_sha: str, setup_sha: str) -> dict:
    """Admit release only from two same-Setup, bounded physical acceptance receipts.

    This function never manufactures visual/function PASS. Both receipts must
    be independently produced against the immutable candidate and remain
    non-release subreceipts until this final gate binds them together.
    """
    require(type(visual) is dict and visual.get("schema") == FINAL_VISUAL_SCHEMA,
            "E07_FINAL_VISUAL_RECEIPT_SCHEMA_HOLD")
    require(visual.get("source_sha") == source_sha and
            visual.get("setup_sha256") == setup_sha and
            visual.get("release_accepted") is False,
            "E07_FINAL_VISUAL_IDENTITY_HOLD")
    require(visual.get("physical_capture") == "PASS" and
            visual.get("d02_visual") == "PASS" and
            visual.get("adaptive_layout") == "PASS" and
            visual.get("reduced_motion") == "PASS" and
            type(visual.get("screenshot_sha256")) is str and
            re.fullmatch(r"[0-9a-f]{64}", visual["screenshot_sha256"]) is not None,
            "E07_FINAL_VISUAL_ACCEPTANCE_HOLD")

    require(type(functions) is dict and
            functions.get("schema") == FINAL_FUNCTION_SCHEMA,
            "E07_FINAL_FUNCTION_RECEIPT_SCHEMA_HOLD")
    require(functions.get("source_sha") == source_sha and
            functions.get("setup_sha256") == setup_sha and
            functions.get("release_accepted") is False,
            "E07_FINAL_FUNCTION_IDENTITY_HOLD")
    actions = functions.get("actions")
    require(type(actions) is dict and set(actions) == set(FINAL_FUNCTIONS),
            "E07_FINAL_FUNCTION_SET_HOLD")
    accepted = {}
    for action in FINAL_FUNCTIONS:
        item = actions[action]
        require(type(item) is dict and
                item.get("function_verified") == "PASS" and
                item.get("permissions_verified") == "PASS" and
                item.get("result") == "PASS" and
                type(item.get("receipt_sha256")) is str and
                re.fullmatch(r"[0-9a-f]{64}", item["receipt_sha256"]) is not None,
                "E07_FINAL_" + action + "_FUNCTION_HOLD")
        accepted[action] = "PASS"
    return {
        "status": "PASS",
        "source_sha": source_sha,
        "setup_sha256": setup_sha,
        "visual": "PASS",
        "adaptive_layout": "PASS",
        "reduced_motion": "PASS",
        "privileged_functions": accepted,
        "scope": "SAME_SETUP_VISUAL_AND_FUNCTION_ACCEPTANCE",
    }


def load_final_acceptance_receipt(path: Path | None, code: str) -> dict:
    """Read only a small regular JSON subreceipt; no missing/stale evidence is accepted."""
    require(path is not None and clean_file(path) and
            1 <= path.stat().st_size <= 1048576, code)
    return _read_locked_e06_json(path)

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


def lifecycle(setup: Path, result: dict, *, frozen_source: str = "", physical_nav: bool = False,
              final_probe_dir: Path | None = None) -> None:
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
    def physical_final_probe(hwnd: int) -> dict:
        # Source-only scripts or old-Setup receipts cannot replace installed
        # same-WPF measurements. The probe emits both subreceipts only on success.
        from probe_final_same_setup import run as probe_run
        require(final_probe_dir is not None, "E07_FINAL_EVIDENCE_DIR_REQUIRED")
        visual, functions = probe_run(hwnd, install, local, source_sha=frozen_source,
                                      setup_sha=sha256(setup), out_dir=final_probe_dir)
        for name, value in (("VISUAL", visual), ("FUNCTIONS", functions)):
            target = final_probe_dir / ("E07_FINAL_"+name+".json")
            require(not target.exists(), "E07_FINAL_RECEIPT_COLLISION_HOLD")
            target.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
        return {"status":"PASS", "source_sha":frozen_source, "setup_sha256":sha256(setup),
                "visual_receipt":"E07_FINAL_VISUAL.json", "function_receipt":"E07_FINAL_FUNCTIONS.json"}

    result["checks"]["installed_gui"] = gui_hwnd(
        install/"NOX.P01.Shell.exe", local,
        safe_nav=physical_nav or frozen_source == "e888941626191c17d19d372889b1f96842c15e1b",
        final_probe=physical_final_probe if final_probe_dir is not None else None)
    result["checks"]["installed_final_physical"] = result["checks"]["installed_gui"].get(
        "final_physical_witness", {"status":"HOLD", "error":"E07_FINAL_PHYSICAL_NOT_RUN"})
    # LIVE Qwen, nonempty persisted SQLite and in-flight STOP must be
    # measured BEFORE this exact installed Setup undergoes update/uninstall.
    # A provider-offline HOLD must never skip conservative lifecycle cleanup.
    if frozen_source in (SOURCE_SHA, NEW_D02_SOURCE_SHA, F842_D02_SOURCE_SHA):
        try:
            result["checks"]["installed_live_qwen_stream_stop_sqlite"] = (
                installed_live_qwen_gates(
                    install/"Backend"/"NOX_HELION_PRIVATE_CANDIDATE.exe"))
        except (Hold, subprocess.TimeoutExpired, OSError, ValueError) as exc:
            result["checks"]["installed_live_qwen_stream_stop_sqlite"] = {
                "status": "HOLD", "error": str(exc) if isinstance(exc, Hold)
                else "E07_LIVE_QWEN_"+type(exc).__name__.upper()+"_HOLD"}

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
    p.add_argument("--artifact-kind",choices=("d02","d02-91a6","d02-f842","original","original-e888","original-30a"),default="d02")
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--visual-receipt",type=Path)
    p.add_argument("--function-receipt",type=Path)
    args=p.parse_args()
    frozen_ids = {
        "original": (ORIGINAL_E06_SOURCE, ORIGINAL_E06_SETUP_SHA),
        "original-e888": (
            "e888941626191c17d19d372889b1f96842c15e1b",
            "96ff9b47ca12a21017374e527786eda8b8fbf2b0e62cc6cfea1f59182cc8e61b"),
        "original-30a": (
            "30a4f7c43649e3c3d66d0d46ec370b2105a69faa",
            "ceb4aab254a6a61b16b25a225ba443149bf1260c3ac410f0c00047842ab9c48c"),
    }
    if args.artifact_kind == "d02-f842":
        source_sha, setup_sha = F842_D02_SOURCE_SHA, F842_D02_SETUP_SHA
    elif args.artifact_kind == "d02-91a6":
        source_sha, setup_sha = NEW_D02_SOURCE_SHA, NEW_D02_SETUP_SHA
    else:
        source_sha, setup_sha = frozen_ids.get(args.artifact_kind, (SOURCE_SHA, SETUP_SHA))
    result={"schema":"NOX-EXPRESS-INDEPENDENT-E07-CANDIDATE-v1",
            "source_sha":source_sha,
            "setup_sha256":setup_sha,
            "checks":{},"release_accepted":False,"independent_e07":"HOLD",
            "error":"NOT_RUN"}
    try:
        require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_HOST_NOT_AUTHORIZED")
        source = args.artifact_dir
        if args.artifact_kind in frozen_ids:
            setup=source/"NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe"
            result["checks"]["artifact"] = setup_lock_original(
                setup,source,frozen={"original-e888":"e888","original-30a":"30a"}.get(args.artifact_kind,"legacy"))
        else:
            setup=source/"e06"/"onehost-wow-diagnostic"/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
            receipt=source/"e06"/"onehost-wow-diagnostic"/"E07_BUILT_HANDOFF.json"
            result["checks"]["artifact"] = setup_lock(setup,receipt,candidate=args.artifact_kind)
        # All physical final witnesses are created on this one installed Setup,
        # not imported from an unrelated workflow or a previous candidate.
        physical_dir = args.out.parent / "same-setup-final"
        lifecycle(setup,result,frozen_source=source_sha,
                  physical_nav=args.artifact_kind in ("original-30a", "d02", "d02-91a6", "d02-f842"),
                  final_probe_dir=physical_dir if args.artifact_kind in ("d02", "d02-91a6", "d02-f842") else None)
        # The complete physical install/update/rollback/uninstall lifecycle ran
        # on this exact Setup. These facts do NOT prove inference or final E07.
        result["checks"]["installed_lifecycle"] = {
            "status": "PASS",
            "scope": "SAME_SETUP_INSTALL_UPDATE_ROLLBACK_UNINSTALL_NO_LOSS",
            "release_accepted": False,
        }
        # The original GUI probe returns real Windows UIA witnesses, but its
        # navigation errors are intentionally nonfatal to conservative cleanup.
        # Evaluate them strictly AFTER cleanup, on this same physical install.
        # Never infer five functioning buttons from their mere presence.
        from probe_five_primary_action import evaluate as evaluate_primary
        result["checks"]["installed_five_primary_actions"] = evaluate_primary(
            result["checks"]["installed_gui"])
        # A successful idle STOP and empty SQLite history are useful physical
        # facts, but not an interrupted live model stream.
        store = result["checks"].get("installed_native_store_stop")
        require(type(store) is dict and store.get("status") == "PASS",
                "E07_NATIVE_STORE_STOP_NOT_ACCEPTED")
        live = result["checks"].get("installed_live_qwen_stream_stop_sqlite")
        require(type(live) is dict and live.get("status") == "PASS",
                "E07_LIVE_QWEN_STREAM_STOP_SQLITE_NOT_ACCEPTED")
        # Final release is admitted only when independently produced same-Setup
        # visual and functional subreceipts are supplied and pass strict shape,
        # identity and per-action checks. Missing evidence stays HOLD.
        if args.artifact_kind in ("d02", "d02-91a6", "d02-f842"):
            witness = result["checks"].get("installed_final_physical", {})
            require(witness.get("status") == "PASS" and
                    witness.get("setup_sha256") == setup_sha and
                    witness.get("source_sha") == source_sha,
                    witness.get("error", "E07_FINAL_SAME_SETUP_PHYSICAL_HOLD"))
            visual_path = physical_dir / "E07_FINAL_VISUAL.json"
            function_path = physical_dir / "E07_FINAL_FUNCTIONS.json"
        else:
            visual_path, function_path = args.visual_receipt, args.function_receipt
        visual_receipt = load_final_acceptance_receipt(
            visual_path, "E07_FINAL_VISUAL_RECEIPT_NOT_PROVIDED")
        function_receipt = load_final_acceptance_receipt(
            function_path, "E07_FINAL_FUNCTION_RECEIPT_NOT_PROVIDED")
        result["checks"]["final_acceptance"] = evaluate_final_acceptance(
            visual_receipt, function_receipt,
            source_sha=source_sha, setup_sha=setup_sha)
        result["release_accepted"] = True
        result["independent_e07"] = "PASS"
        result["error"] = None
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
    # Physical probes must share this CLI module to preserve the Hold class.
    # Importing a second copy incorrectly labels a genuine Hold as unexpected.
    sys.modules["independent_setup_e07"] = sys.modules[__name__]
    raise SystemExit(main())
