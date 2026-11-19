"""NOX V135: additive, source-pinned owner Resonance V24/V22 stream repair.

Creates a NEW release candidate from a verified source ZIP (frozen V29.3
or V134 derived). No server access, model file changes, S03 operations or
production install. Input ZIP is untouched. For V134, provide its exact SHA
as --expected-source-sha, and preserve the original frozen file for no-loss.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import posixpath
import zipfile
from pathlib import Path

FROZEN_SHA = "166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0"
FROZEN_N = 1089
JS = "site/nox-v135-resonance-owner-bridge.js"
OBS_JS = "site/nox-v137-owner-self-status.js"
OBS_SOURCE = Path("coordination/onepass/nox-v137-owner-self-status.js")
NATIVE_SELF_MODULE = "integration/nox_v137_owner_self_observation.py"
NATIVE_SELF_SOURCE = Path("nox_runpod/teacher_mesh/v137/owner_self_observation.py")
NATIVE_RESPONSE_MODULE = "integration/nox_v137_owner_response_contract.py"
NATIVE_RESPONSE_SOURCE = Path("nox_runpod/teacher_mesh/v137/owner_response_contract.py")
MANIFEST = "NOX_V135_OWNER_RESONANCE_STREAM_MANIFEST.json"
CAP_POLICY = "NOX_V135_OWNER_BRIDGE_CAP_POLICY.json"
CAP_POLICY_SOURCE = Path("coordination/onepass/v135_owner_bridge_cap_policy.json")
CAP_POLICY_SHA256 = "74f16458cd7c2e295403d6569c289ec4861b036c60c72065d0ad8560164f2218"
PAGES = ("site/pc/resonance.html", "site/pc/v22/resonance.template.html")
ROLLBACK = "rollback/v135/"
SCRIPT_URL = "/nox-web-v29/nox-v135-resonance-owner-bridge.js"
SCRIPT_TAG = '<script defer src="' + SCRIPT_URL + '" data-nox-owner-v135="1"></script>'
# Immutable v2 policy pins the measured compatibility bridge and a 512-byte reserve.
MAX_OWNER_BRIDGE_BYTES = 25181
EXPECTED_BRIDGE_BYTES = 24669
EXPECTED_BRIDGE_SHA256 = "3de9f87874534e603e4040f4fc10a018679820569431a7a0b230bda035552af3"
OBS_SCRIPT_URL = "/nox-web-v29/nox-v137-owner-self-status.js"
OBS_SCRIPT_TAG = '<script defer src="' + OBS_SCRIPT_URL + '" data-nox-owner-v137="1"></script>'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    with Path(path).open("rb") as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _safe_name(name: str) -> bool:
    return (isinstance(name, str) and not name.startswith("/")
            and "\\" not in name and ".." not in name.split("/")
            and not name.endswith("/../"))


def _zip_file(z: zipfile.ZipFile, name: str, blob: bytes):
    i = zipfile.ZipInfo(name, date_time=(2026, 11, 15, 0, 0, 0))
    i.external_attr = 0o100644 << 16
    i.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(i, blob)


def build(source: Path, frozen: Path, js_file: Path, output: Path,
          *, expected_source_sha: str) -> dict:
    source, frozen, js_file, output = map(Path, (source, frozen, js_file, output))
    if not expected_source_sha or len(expected_source_sha) != 64:
        raise ValueError("HOLD_EXPECTED_SOURCE_SHA")
    actual_source_sha = file_sha(source)
    if actual_source_sha != expected_source_sha:
        raise ValueError("HOLD_SOURCE_SHA_DRIFT")
    if file_sha(frozen) != FROZEN_SHA:
        raise ValueError("HOLD_FROZEN_ORIGINAL_SHA")
    if output.exists() or output.resolve() in (source.resolve(), frozen.resolve()):
        raise ValueError("HOLD_OUTPUT_OVERWRITE")
    policy_bytes = CAP_POLICY_SOURCE.read_bytes()
    if digest(policy_bytes) != CAP_POLICY_SHA256:
        raise ValueError("HOLD_OWNER_BRIDGE_CAP_POLICY_SHA")
    try:
        cap_policy = json.loads(policy_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("HOLD_OWNER_BRIDGE_CAP_POLICY_JSON") from exc
    expected_policy = {
        "schema": "NOX_V135_OWNER_BRIDGE_CAP_POLICY_V2",
        "measured_bridge_bytes": EXPECTED_BRIDGE_BYTES,
        "max_bridge_bytes": MAX_OWNER_BRIDGE_BYTES,
        "reserve_bytes": 512,
        "bridge_sha256": EXPECTED_BRIDGE_SHA256,
    }
    if cap_policy != expected_policy:
        raise ValueError("HOLD_OWNER_BRIDGE_CAP_POLICY_VERSION")
    script = js_file.read_bytes()
    if (len(script) != EXPECTED_BRIDGE_BYTES
            or len(script) > MAX_OWNER_BRIDGE_BYTES
            or digest(script) != EXPECTED_BRIDGE_SHA256):
        raise ValueError("HOLD_OWNER_BRIDGE_BOUNDS")
    if b"window.NOX_NATIVE_OWNER===true" not in script or b"/api/nox/chat/stream" not in script:
        raise ValueError("HOLD_OWNER_BRIDGE_CONTRACT")
    if b"HOLD_DIALOG_HISTORY_READBACK" not in script or b"status:'done'" not in script:
        raise ValueError("HOLD_STREAM_RECEIPT_CONTRACT")
    monitor_js = OBS_SOURCE.read_bytes()
    native_self = NATIVE_SELF_SOURCE.read_bytes()
    native_reply = NATIVE_RESPONSE_SOURCE.read_bytes()
    if (b"window.NOX_NATIVE_OWNER !== true" not in monitor_js
            or b"/api/nox/self/observations" not in monitor_js
            or b"/api/status" not in monitor_js
            or b"HOLD" not in monitor_js):
        raise ValueError("HOLD_V137_REAL_MONITOR_CONTRACT")
    if (b"def register_nox_v137_self_observation(" not in native_self
            or b"subjective_consciousness_established" not in native_self
            or b"positive_optimizer_steps_verified" not in native_self):
        raise ValueError("HOLD_V137_SELF_OBSERVATION_SOURCE")
    compile(native_self, str(NATIVE_SELF_SOURCE), "exec")
    if (b"def build_owner_response_contract(" not in native_reply
            or b"native_cross_chat_sources" not in native_reply
            or b"READY_FOR_EXISTING_SINGLE_MODEL" not in native_reply):
        raise ValueError("HOLD_V137_GROUNDED_RESPONSE_CONTRACT")
    compile(native_reply, str(NATIVE_RESPONSE_SOURCE), "exec")
    temp = output.with_name(output.name + ".pending-v135")
    if temp.exists():
        raise ValueError("HOLD_PENDING_EXISTS")
    changed = {}
    try:
        with zipfile.ZipFile(source) as base, zipfile.ZipFile(frozen) as original:
            source_names, original_names = base.namelist(), original.namelist()
            if (len(original_names) != FROZEN_N
                    or len(set(original_names)) != FROZEN_N
                    or len(set(source_names)) != len(source_names)
                    or any(not _safe_name(n) for n in source_names)):
                raise ValueError("HOLD_ARCHIVE_MEMBER_INTEGRITY")
            if not set(original_names).issubset(source_names):
                raise ValueError("HOLD_ORIGINAL_1089_MEMBER_LOSS")
            if (not set(PAGES).issubset(source_names) or
                    any(name in source_names for name in (JS, OBS_JS, NATIVE_SELF_MODULE, NATIVE_RESPONSE_MODULE, MANIFEST, CAP_POLICY))):
                raise ValueError("HOLD_UNEXPECTED_STAGE_OR_EXISTING_PATCH")
            if base.testzip() is not None or original.testzip() is not None:
                raise ValueError("HOLD_ZIP_CRC")
            with zipfile.ZipFile(temp, "x", allowZip64=True) as release:
                for item in base.infolist():
                    name = item.filename
                    blob = base.read(item)
                    if name in PAGES:
                        html = blob.decode("utf-8")
                        if (html.count("</head>") != 1 or
                                any(q in html for q in ("nox-v135-resonance-owner-bridge.js", "nox-v137-owner-self-status.js"))):
                            raise ValueError("HOLD_HTML_SCRIPT_ANCHOR_" + name)
                        patch = html.replace("</head>", SCRIPT_TAG + "\n" + OBS_SCRIPT_TAG + "\n</head>", 1).encode("utf-8")
                        changed[name] = {"before_sha256": digest(blob), "after_sha256": digest(patch)}
                        release.writestr(copy.copy(item), patch)
                    else:
                        release.writestr(copy.copy(item), blob)
                _zip_file(release, JS, script)
                _zip_file(release, CAP_POLICY, policy_bytes)
                _zip_file(release, OBS_JS, monitor_js)
                _zip_file(release, NATIVE_SELF_MODULE, native_self)
                _zip_file(release, NATIVE_RESPONSE_MODULE, native_reply)
                for name in sorted(PAGES):
                    _zip_file(release, ROLLBACK + name, base.read(name))
                manifest = {
                    "schema": "NOX_V135_OWNER_RESONANCE_NATIVE_STREAM_SOURCE_V1",
                    "instructions_version": "0.0.6",
                    "source_sha256": actual_source_sha,
                    "frozen_source_sha256": FROZEN_SHA,
                    "source_entries": len(source_names),
                    "original_paths_preserved": FROZEN_N,
                    "patched_html": list(PAGES),
                    "added_js": JS,
                    "added_js_sha256": digest(script),
                    "added_js_bytes": len(script),
                    "owner_bridge_cap_policy": {
                        "schema": cap_policy["schema"],
                        "sha256": CAP_POLICY_SHA256,
                        "measured_bridge_bytes": cap_policy["measured_bridge_bytes"],
                        "max_bridge_bytes": cap_policy["max_bridge_bytes"],
                        "reserve_bytes": cap_policy["reserve_bytes"],
                    },
                    "added_cap_policy": CAP_POLICY,
                    "added_status_js": OBS_JS,
                    "added_status_js_sha256": digest(monitor_js),
                    "added_owner_self_observer": NATIVE_SELF_MODULE,
                    "added_owner_self_observer_sha256": digest(native_self),
                    "added_owner_response_contract": NATIVE_RESPONSE_MODULE,
                    "added_owner_response_contract_sha256": digest(native_reply),
                    "native_observer_attached_in_live_onehost": False,
                    "process_control_actions_enabled": False,
                    "rollback_dir": ROLLBACK,
                    "original_source_unchanged": True,
                    "native_owner_only": True,
                    "existing_onehost_only": True,
                    "no_duplicate_backend": True,
                    "no_new_model": True,
                    "no_new_memory_database": True,
                    "original_S03_unchanged": True,
                    "full_weight_training_unchanged": True,
                    "production_deployed": False,
                    "live_ttft_confirmed": False,
                    "patches": changed,
                }
                _zip_file(release, MANIFEST,
                          (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
                           + "\n").encode("utf-8"))
        proof = verify(temp, source=source, frozen=frozen)
        os.link(temp, output)
        temp.unlink()
        return {"state": "NOX_V135_VERIFIED_SOURCE_ONLY", "output": str(output),
                "sha256": file_sha(output), **proof}
    finally:
        temp.unlink(missing_ok=True)


def verify(output: Path, *, source: Path, frozen: Path) -> dict:
    with zipfile.ZipFile(source) as base, zipfile.ZipFile(frozen) as original, zipfile.ZipFile(output) as patch:
        if patch.testzip() is not None:
            raise ValueError("HOLD_OUTPUT_CRC")
        manifest = json.loads(patch.read(MANIFEST))
        if (manifest.get("schema") != "NOX_V135_OWNER_RESONANCE_NATIVE_STREAM_SOURCE_V1"
                or manifest.get("production_deployed") is not False
                or manifest.get("original_paths_preserved") != FROZEN_N):
            raise ValueError("HOLD_MANIFEST")
        source_names = base.namelist()
        out_names = patch.namelist()
        if (len(out_names) != len(source_names) + len(PAGES) + 6
                or len(set(out_names)) != len(out_names)
                or not set(original.namelist()).issubset(out_names)):
            raise ValueError("HOLD_TOTAL_MEMBERS")
        for name in source_names:
            if name in PAGES:
                patchinfo = manifest["patches"][name]
                if (digest(patch.read(name)) != patchinfo["after_sha256"]
                        or digest(base.read(name)) != patchinfo["before_sha256"]
                        or patch.read(ROLLBACK + name) != base.read(name)
                        or SCRIPT_URL.encode() not in patch.read(name)
                        or OBS_SCRIPT_URL.encode() not in patch.read(name)):
                    raise ValueError("HOLD_PATCH_OR_ROLLBACK_" + name)
            elif patch.read(name) != base.read(name):
                raise ValueError("HOLD_SOURCE_FILE_MODIFIED_" + name)
        policy_blob = patch.read(CAP_POLICY)
        if (digest(policy_blob) != CAP_POLICY_SHA256
                or policy_blob != CAP_POLICY_SOURCE.read_bytes()):
            raise ValueError("HOLD_OWNER_BRIDGE_CAP_POLICY_SHA")
        cap_policy = json.loads(policy_blob)
        policy_manifest = manifest.get("owner_bridge_cap_policy")
        if (policy_manifest != {
                "schema": cap_policy["schema"],
                "sha256": CAP_POLICY_SHA256,
                "measured_bridge_bytes": cap_policy["measured_bridge_bytes"],
                "max_bridge_bytes": cap_policy["max_bridge_bytes"],
                "reserve_bytes": cap_policy["reserve_bytes"],
        }):
            raise ValueError("HOLD_OWNER_BRIDGE_CAP_MANIFEST")
        bridge_blob = patch.read(JS)
        if (digest(bridge_blob) != manifest["added_js_sha256"]
                or digest(bridge_blob) != cap_policy["bridge_sha256"]
                or len(bridge_blob) != cap_policy["measured_bridge_bytes"]
                or len(bridge_blob) != manifest.get("added_js_bytes")
                or len(bridge_blob) > cap_policy["max_bridge_bytes"]):
            raise ValueError("HOLD_SCRIPT_HASH")
        if (digest(patch.read(OBS_JS)) != manifest.get("added_status_js_sha256")
                or digest(patch.read(NATIVE_SELF_MODULE)) != manifest.get("added_owner_self_observer_sha256")
                or digest(patch.read(NATIVE_RESPONSE_MODULE)) != manifest.get("added_owner_response_contract_sha256")):
            raise ValueError("HOLD_NATIVE_SELF_MONITOR_HASH")
        return {"source_entries": len(source_names), "output_entries": len(out_names),
                "unchanged_source_entries": len(source_names)-len(PAGES),
                "original_frozen_entries_retained": FROZEN_N,
                "owner_resonance_pages_patched": len(PAGES),
                "rollback_bytes_verified": True, "real_server_modified": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--frozen", type=Path, required=True)
    p.add_argument("--script", type=Path,
                   default=Path("coordination/onepass/nox-v135-resonance-owner-bridge.js"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-source-sha", required=True)
    a = p.parse_args()
    result = build(a.source, a.frozen, a.script, a.output,
                   expected_source_sha=a.expected_source_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
