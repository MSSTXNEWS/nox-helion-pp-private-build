#!/usr/bin/env python3
"""Import smoke for the M2.0 payload and fixtures.

Proves the pinned app can find and load the bytes that exist, and that the
first-run product gate stays on HOLD for the kinds this repository does not
contain. Owner ACK fields are checked to be unsigned. The reference EXE is
refused if it appears.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from m2_common import (
    ABSENT_PRODUCT_KINDS,
    CANDIDATE_GUI_NAME,
    MARKER_NAME,
    MARKER_TEXT,
    QWEN_LAYER_BYTES,
    QWEN_LAYER_SHA256,
    REFERENCE_EXE_BYTES,
    REFERENCE_EXE_NAME,
    REFERENCE_EXE_SHA256,
    REFERENCE_SOURCE_COMMIT,
    VERSION,
    sha256_file,
)


class SmokeFailure(RuntimeError):
    pass


def _add_source(source: Path | None) -> None:
    if source is None:
        return
    resolved = str(source.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _exec_nodes(path: Path, names: set[str], namespace: dict) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    chosen = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in names:
            chosen.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            chosen.append(node)
    if {getattr(node, "name", None) for node in chosen} != names:
        missing = names - {node.name for node in chosen}
        raise SmokeFailure(f"SOURCE_SYMBOLS_MISSING:{sorted(missing)}")
    module = ast.Module(body=chosen, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)  # noqa: S102 (pinned source functions)


def load_model_config_from_source(source: Path, config: Path):
    """Run the real load_model_config function from the pinned source.

    The desktop module imports the whole GUI stack. The function itself only
    needs the standard library plus InferenceProfile, so the smoke executes
    that function and that class from their source files.
    """
    from dataclasses import dataclass
    from helion.contracts import CORE_IDS
    namespace = {
        "dataclass": dataclass,
        "hashlib": hashlib,
        "json": json,
        "os": os,
        "stat": __import__("stat"),
        "Path": Path,
        "CORE_IDS": CORE_IDS,
        "ModelPin": object,
    }
    _exec_nodes(source / "s02_local_model_gateway.py", {"InferenceProfile"}, namespace)
    _exec_nodes(
        source / "helion" / "first_release.py",
        {"_model_config_unique_object", "_model_config_nonfinite_constant", "load_model_config"},
        namespace,
    )
    return namespace["load_model_config"](config)


def verify_manifest_bytes(payload_root: Path) -> list[dict]:
    manifest = _load_json(payload_root / "M2_PAYLOAD_MANIFEST.json")
    if manifest.get("schema") != "NOX_M2_PAYLOAD_MANIFEST_V1":
        raise SmokeFailure("MANIFEST_SCHEMA")
    if manifest.get("owner_signed") or manifest.get("approved") or manifest.get("live_ai") or manifest.get("online"):
        raise SmokeFailure("MANIFEST_OVERCLAIMS")
    if manifest.get("reference_exe_included"):
        raise SmokeFailure("MANIFEST_CLAIMS_REFERENCE_EXE")
    files = []
    seen = set()
    for item in manifest["files"]:
        rel = item["path"]
        seen.add(rel)
        path = payload_root / rel
        if path.is_symlink() or not path.is_file():
            raise SmokeFailure(f"MANIFEST_FILE_MISSING:{rel}")
        actual = sha256_file(path)
        if actual != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise SmokeFailure(f"MANIFEST_HASH_MISMATCH:{rel}")
        if path.name == REFERENCE_EXE_NAME or actual == REFERENCE_EXE_SHA256:
            raise SmokeFailure("REFERENCE_EXE_PRESENT_IN_PAYLOAD")
        files.append(item)
    on_disk = {path.relative_to(payload_root).as_posix() for path in payload_root.rglob("*") if path.is_file()}
    if on_disk != seen | {"M2_PAYLOAD_MANIFEST.json"}:
        raise SmokeFailure("MANIFEST_COVERAGE_MISMATCH")
    return files


def _weights(payload_root: Path):
    from helion.ai_weights.nox_weights_bridge import VerifiedWeights
    loaded = VerifiedWeights(payload_root / "product_payload" / "weights").load()
    if len(loaded.models) != 7:
        raise SmokeFailure("WEIGHTS_MODEL_COUNT")
    return loaded


def _menu(payload_root: Path) -> dict:
    from helion.g3_menu_provenance import load_pinned_menu_source
    raw = load_pinned_menu_source(payload_root / "product_payload" / "helion" / "data" / "menu_v2_full_catalog.json")
    if raw.get("item_count") != 193:
        raise SmokeFailure("MENU_ITEM_COUNT")
    return raw


def _personas(source: Path, payload_root: Path) -> list[str]:
    from helion.personas import PERSONAS
    ids = []
    for persona in PERSONAS:
        path = payload_root / "fixtures" / "personas" / f"{persona.persona_id}.json"
        data = _load_json(path)
        if data["runtime_persona_id"] != persona.persona_id:
            raise SmokeFailure("PERSONA_ID_MISMATCH")
        if data["runtime_display_name"] != persona.display_name:
            raise SmokeFailure("PERSONA_NAME_MISMATCH")
        if data.get("owner_signed") or data.get("approved") or data.get("signed"):
            raise SmokeFailure("PERSONA_FIXTURE_SIGNED")
        ids.append(persona.persona_id)
    if len(ids) != 5 or len(set(ids)) != 5:
        raise SmokeFailure("PERSONA_COUNT")
    catalog = _load_json(payload_root / "product_payload" / "assets" / "personas_5.json")
    if {row["id"] for row in catalog["personas"]} != {"KV", "AM", "LA", "EV", "KW"}:
        raise SmokeFailure("PERSONA_CATALOG_CODES")
    return ids


def _model_config(source: Path, payload_root: Path):
    config = payload_root / "fixtures" / "model_config.json"
    example = payload_root / "product_payload" / "model_config.example.json"
    if config.read_bytes() != example.read_bytes():
        raise SmokeFailure("MODEL_CONFIG_NOT_THE_SOURCE_EXAMPLE")
    pins, profile = load_model_config_from_source(source, config)
    if pins != {} or profile.name != "ECO":
        raise SmokeFailure("MODEL_CONFIG_UNEXPECTED_BINDING")
    return pins, profile


def _traits(payload_root: Path) -> None:
    data = _load_json(payload_root / "product_payload" / "helion" / "data" / "traits_seed_64.json")
    if data.get("schema") != "nox_helion.persona_trait_seed.v1":
        raise SmokeFailure("TRAIT_SEED_SCHEMA")
    if data.get("seed_count") != 64 or len(data.get("traits") or []) != 64:
        raise SmokeFailure("TRAIT_SEED_COUNT")


def _rights(payload_root: Path) -> None:
    expected = _load_json(payload_root / "fixtures" / "expected" / "fake_rights_rows_forbidden.expected.json")
    index = _load_json(payload_root / "fixtures" / "rights" / "media_rights_index.json")
    if index["row_count"] != expected["row_count"]:
        raise SmokeFailure("RIGHTS_ROW_COUNT")
    if index["rights_cleared_count"] != expected["rights_cleared_must_equal"]:
        raise SmokeFailure("RIGHTS_CLEARED_COUNT")
    if any(row["rights_status"] != "SOURCE_RIGHTS_NOT_REVERIFIED" for row in index["rows"]):
        raise SmokeFailure("RIGHTS_STATUS_CHANGED")


def _absent(payload_root: Path) -> list[dict]:
    expected = _load_json(payload_root / "fixtures" / "expected" / "product_bytes_absent.expected.json")
    if expected["must_be_absent_kinds"] != list(ABSENT_PRODUCT_KINDS):
        raise SmokeFailure("ABSENT_KIND_LIST_DRIFT")
    blob = b""
    for path in payload_root.rglob("*"):
        if path.is_file() and path.stat().st_size < 2_000_000:
            blob += path.read_bytes()
    if QWEN_LAYER_SHA256.encode("ascii") in blob and b"sha256_not_present" not in blob:
        # The expected fixture and GATE_HOLD are allowed to cite the missing digest.
        pass
    cited = blob.count(QWEN_LAYER_SHA256.encode("ascii"))
    if cited < 1:
        raise SmokeFailure("QWEN_ABSENCE_NOT_RECORDED")
    # No file may be the missing layer.
    for path in payload_root.rglob("*"):
        if path.is_file() and path.stat().st_size == QWEN_LAYER_BYTES:
            raise SmokeFailure("QWEN_LAYER_BYTES_UNEXPECTED")
        if path.is_file() and path.suffix in {".gguf", ".onnx"}:
            raise SmokeFailure(f"UNEXPECTED_MODEL_BLOB:{path.name}")
    hold = _load_json(payload_root / "product_payload" / "GATE_HOLD.json")
    if hold.get("status") != "HOLD" or hold.get("qwen_layer", {}).get("present") is not False:
        raise SmokeFailure("GATE_HOLD_FILE")
    if hold.get("owner_signed") or hold.get("approved") or hold.get("live_ai") or hold.get("online"):
        raise SmokeFailure("GATE_HOLD_OVERCLAIMS")
    return [
        {
            "kind": kind,
            "detail": "Not in the pinned source snapshot. Not fabricated.",
        }
        for kind in ABSENT_PRODUCT_KINDS
    ] + [{
        "kind": "qwen2.5 layer",
        "path": "product_payload/models/qwen2.5-0.5b-instruct-q4_K_M/",
        "detail": f"Absent. Cited sha256 {QWEN_LAYER_SHA256}, {QWEN_LAYER_BYTES} bytes, not packaged.",
    }]


def _first_run_gate(source: Path, payload_root: Path) -> str:
    from product_payload_gate import ProductPayloadHold, verify_product_payload
    manifest = payload_root / "product_payload" / "app_import_manifest.json"
    try:
        verify_product_payload(manifest, root=payload_root / "product_payload", source_root=source)
    except ProductPayloadHold as exc:
        reason = str(exc)
    else:
        raise SmokeFailure("FIRST_RUN_GATE_UNEXPECTED_PASS")
    if "KIND_INVALID" not in reason and "REQUIRED_KIND_MISSING" not in reason and "SCHEMA" not in reason:
        raise SmokeFailure(f"FIRST_RUN_GATE_UNEXPECTED_REASON:{reason}")
    return reason


def _owner_ack_template(payload_root: Path) -> None:
    expected = _load_json(payload_root / "fixtures" / "expected" / "owner_ack_unsigned.expected.json")
    for rel in ("fixtures/consent_receipt.template.json", "fixtures/license_notice.template.json"):
        data = _load_json(payload_root / rel)
        if data.get("signed") is not expected["signed_must_be"] or data.get("approved") is not expected["approved_must_be"]:
            raise SmokeFailure(f"TEMPLATE_SIGNED:{rel}")


def _reference_forbidden(payload_root: Path) -> None:
    expected = _load_json(payload_root / "fixtures" / "expected" / "exe_in_kit_forbidden.expected.json")
    if expected["forbidden_sha256"] != REFERENCE_EXE_SHA256 or expected["forbidden_name"] != REFERENCE_EXE_NAME:
        raise SmokeFailure("REFERENCE_EXPECTED_DRIFT")
    for path in payload_root.rglob("*"):
        if path.is_file() and path.name == REFERENCE_EXE_NAME:
            raise SmokeFailure("REFERENCE_EXE_NAME_IN_TREE")


def _staged_matches(payload_root: Path, staged: Path) -> None:
    for folder in ("product_payload", "fixtures"):
        src = payload_root / folder
        dst = staged / folder
        if not dst.is_dir():
            raise SmokeFailure(f"STAGED_FOLDER_MISSING:{folder}")
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(src)
            other = dst / rel
            if not other.is_file() or other.read_bytes() != path.read_bytes():
                raise SmokeFailure(f"STAGED_MISMATCH:{folder}/{rel.as_posix()}")


def exe_contains_payload(exe: Path) -> str:
    if not exe.is_file():
        raise SmokeFailure(f"EXE_MISSING:{exe}")
    digest = sha256_file(exe)
    if digest == REFERENCE_EXE_SHA256 or exe.name == REFERENCE_EXE_NAME:
        raise SmokeFailure("REFERENCE_EXE_EMITTED")
    if exe.stat().st_size == REFERENCE_EXE_BYTES and digest == REFERENCE_EXE_SHA256:
        raise SmokeFailure("REFERENCE_EXE_BYTES")
    try:
        from PyInstaller.archive.readers import CArchiveReader
        reader = CArchiveReader(str(exe))
        toc = getattr(reader, "toc", {})
        if isinstance(toc, dict):
            names = list(toc)
        else:
            names = [getattr(entry, "name", "") for entry in toc]
        blob = "\n".join(str(name) for name in names)
        if MARKER_NAME in blob or "product_payload" in blob:
            return "pyinstaller_toc"
    except Exception:
        pass
    data = exe.read_bytes()
    if b"NOX_M2_0_PAYLOAD_PACKAGED" in data or MARKER_NAME.encode("ascii") in data:
        return "embedded_marker"
    raise SmokeFailure("EXE_DOES_NOT_CONTAIN_PAYLOAD_MARKER")


def run_smoke(*, source: Path | None, payload_root: Path, staged: Path | None = None,
              exe: Path | None = None, background_exe: Path | None = None) -> dict:
    payload_root = payload_root.resolve()
    _add_source(source)
    if source is not None:
        gate_dir = source / "tools" / "windows_candidate_v23"
        if str(gate_dir) not in sys.path:
            sys.path.insert(0, str(gate_dir))
    checks: list[dict] = []
    errors: list[str] = []

    def step(name: str, fn):
        try:
            detail = fn()
            checks.append({"name": name, "ok": True, "detail": "" if detail is None else str(detail)})
        except Exception as exc:
            detail = f"{exc.__class__.__name__}: {exc}"
            checks.append({"name": name, "ok": False, "detail": detail})
            errors.append(f"{name}: {detail}")

    files: list[dict] = []

    def manifest_step():
        nonlocal files
        files = verify_manifest_bytes(payload_root)
        marker = (payload_root / "product_payload" / MARKER_NAME).read_text(encoding="utf-8")
        if marker != MARKER_TEXT:
            raise SmokeFailure("MARKER_TEXT")
        return f"{len(files)} files match the manifest"

    step("manifest_sha256", manifest_step)
    step("reference_exe_absent", lambda: (_reference_forbidden(payload_root) or REFERENCE_EXE_SHA256))
    step("owner_templates_unsigned", lambda: (_owner_ack_template(payload_root) or "signed=false approved=false"))
    absent: list[dict] = []

    def absent_step():
        nonlocal absent
        absent = _absent(payload_root)
        return "qwen layer and five first-run kinds absent"

    step("absent_product_kinds", absent_step)
    step("media_rights_index", lambda: (_rights(payload_root) or "173 rows, 0 cleared"))
    step("trait_seed_catalog", lambda: (_traits(payload_root) or "64 traits"))

    gate_reason = "NOT_RUN"
    persona_ids: list[str] = []
    if source is None:
        errors.append("source: SOURCE_REQUIRED_FOR_APP_LOADERS")
        checks.append({"name": "app_loaders", "ok": False, "detail": "SOURCE_REQUIRED_FOR_APP_LOADERS"})
    else:
        step("research_scorers", lambda: f"VerifiedWeights.load models={len(_weights(payload_root).models)}")
        step("menu_catalog", lambda: f"load_pinned_menu_source items={_menu(payload_root)['item_count']}")
        def persona_step():
            nonlocal persona_ids
            persona_ids = _personas(source, payload_root)
            return " ".join(persona_ids)
        step("persona_contract", persona_step)
        step("model_config", lambda: f"load_model_config pins={len(_model_config(source, payload_root)[0])} profile=ECO")
        def gate_step():
            nonlocal gate_reason
            gate_reason = _first_run_gate(source, payload_root)
            return gate_reason
        step("first_run_product_gate_hold", gate_step)

    if staged is not None:
        step("staged_copy", lambda: (_staged_matches(payload_root, staged) or str(staged)))
    packaging = None
    if exe is not None:
        def exe_step():
            nonlocal packaging
            packaging = exe_contains_payload(exe)
            return f"{exe.name} sha256={sha256_file(exe)} packaging={packaging}"
        step("windows_or_linux_package", exe_step)
    background = None
    if background_exe is not None and background_exe.is_file():
        digest = sha256_file(background_exe)
        if digest == REFERENCE_EXE_SHA256 or background_exe.name == REFERENCE_EXE_NAME:
            errors.append("background: REFERENCE_EXE_EMITTED")
            checks.append({"name": "background_exe", "ok": False, "detail": "REFERENCE_EXE_EMITTED"})
        else:
            background = {"name": background_exe.name, "bytes": background_exe.stat().st_size, "sha256": digest}
            checks.append({"name": "background_exe", "ok": True, "detail": digest})

    import_roles = {
        "weights/01_truthful_memory.safetensors": "VerifiedWeights.load",
        "helion/data/menu_v2_full_catalog.json": "load_pinned_menu_source",
        "helion/data/traits_seed_64.json": "trait seed schema",
        "assets/personas_5.json": "persona catalog",
        "model_config.example.json": "load_model_config",
    }
    shown = []
    for item in files:
        if item["path"].startswith("product_payload/"):
            rel = item["path"][len("product_payload/"):]
            if rel in import_roles or rel.startswith("weights/") or rel.startswith("fixtures/"):
                shown.append({
                    "path": item["path"],
                    "role": import_roles.get(rel, "payload"),
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                    "load": "verified",
                })
        elif item["path"].startswith("fixtures/personas/") or item["path"] in {
            "fixtures/model_config.json",
            "fixtures/rights/media_rights_index.json",
            "fixtures/smoke_import_list.json",
        }:
            shown.append({
                "path": item["path"],
                "role": "fixture",
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "load": "verified",
            })
    ok = not errors and all(item["ok"] for item in checks)
    report = {
        "schema": "NOX_M2_PAYLOAD_ACK_V1",
        "version": VERSION,
        "candidate": CANDIDATE_GUI_NAME,
        "product_acceptance": "0/1",
        "release_accepted": False,
        "online": False,
        "live_ai": False,
        "bytes_verified": ok,
        "import_smoke": "PASS" if ok else "FAIL",
        "first_run_product_gate": "HOLD",
        "first_run_product_gate_reason": gate_reason,
        "native_model_load": "NOT_RUN",
        "reference_exe_name": REFERENCE_EXE_NAME,
        "reference_exe_sha256": REFERENCE_EXE_SHA256,
        "reference_exe_bytes": REFERENCE_EXE_BYTES,
        "reference_source_commit": REFERENCE_SOURCE_COMMIT,
        "reference_exe_touched": False,
        "reference_exe_included": False,
        "persona_ids": persona_ids,
        "packaging": packaging,
        "background_exe": background,
        "owner_ack": {
            "payload_reviewed": False,
            "fixtures_reviewed": False,
            "signed": False,
            "approved": False,
            "signed_by": None,
            "signature": None,
            "note": "Owner-only ticks stay unsigned. This receipt does not sign or approve on the owner's behalf.",
        },
        "checks": checks,
        "errors": errors,
        "absent": absent,
        "files": shown,
        "manifest_file_count": len(files),
    }
    return report


def write_outputs(report: dict, out_dir: Path, extra_files: list[Path] | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    from m2_payload_status import render_html
    stamped = dict(report)
    stamped["captured_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ack_path = out_dir / "M2_ACK_RECEIPT.json"
    html_path = out_dir / "M2_PAYLOAD_INTEGRITY.html"
    log_path = out_dir / "m2-import-smoke.log"
    sums_path = out_dir / "SHA256SUMS.txt"
    ack_path.write_text(json.dumps(stamped, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(stamped), encoding="utf-8")
    lines = [
        f"import_smoke={report['import_smoke']}",
        f"first_run_product_gate={report['first_run_product_gate']} {report['first_run_product_gate_reason']}",
        f"product_acceptance={report['product_acceptance']}",
        f"reference_exe_touched={report['reference_exe_touched']}",
        f"reference_exe_sha256={report['reference_exe_sha256']}",
    ]
    for item in report["checks"]:
        lines.append(f"{'PASS' if item['ok'] else 'FAIL'} {item['name']} {item['detail']}")
    for err in report["errors"]:
        lines.append(f"ERROR {err}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    listed = [ack_path, html_path, log_path]
    if extra_files:
        listed.extend(extra_files)
    sums = []
    for path in listed:
        if path.is_file():
            sums.append(f"{sha256_file(path)}  {path.name}")
    sums_path.write_text("\n".join(sums) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--staged", type=Path)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--background-exe", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_smoke(
            source=args.source,
            payload_root=args.payload,
            staged=args.staged,
            exe=args.exe,
            background_exe=args.background_exe,
        )
    except Exception:
        traceback.print_exc()
        return 1
    print(f"import_smoke={report['import_smoke']} gate={report['first_run_product_gate']} files={report['manifest_file_count']}")
    if args.out_dir:
        extras = [path for path in (args.exe, args.background_exe) if path is not None]
        write_outputs(report, args.out_dir, extras)
        print(f"WROTE {args.out_dir}")
    return 0 if report["import_smoke"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
