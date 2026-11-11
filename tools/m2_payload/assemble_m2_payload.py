#!/usr/bin/env python3
"""Build M2.0 product_payload and fixtures from the pinned source tree.

Copies bytes that already exist in the source snapshot. Does not invent a
Qwen layer, tokenizer, adapter, RAG index, cultural index, license grant, or
owner signature. Research scorers stay labeled as research scorers.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from m2_common import (
    ABSENT_PRODUCT_KINDS,
    MARKER_NAME,
    MARKER_TEXT,
    PERSONA_CODES,
    QWEN_LAYER_BYTES,
    QWEN_LAYER_SHA256,
    QWEN_MODEL_TAG,
    REFERENCE_EXE_BYTES,
    REFERENCE_EXE_NAME,
    REFERENCE_EXE_SHA256,
    REFERENCE_SOURCE_COMMIT,
    VERSION,
    DEFAULT_PAYLOAD_ROOT,
    sha256_bytes,
    sha256_file,
)


SOURCE_COPIES = (
    ("helion/ai_weights/weights", "product_payload/weights"),
    ("helion/data/traits_seed_64.json", "product_payload/helion/data/traits_seed_64.json"),
    ("helion/data/menu_v2_full_catalog.json", "product_payload/helion/data/menu_v2_full_catalog.json"),
    ("assets/personas_5.json", "product_payload/assets/personas_5.json"),
    ("assets/asset_manifest.json", "product_payload/assets/asset_manifest.json"),
    ("model_config.example.json", "product_payload/model_config.example.json"),
    ("docs/media_source_inventory_20261020.csv", "fixtures/rights/media_source_inventory_20261020.csv"),
)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_text(path: Path, text: str) -> None:
    _write_bytes(path, text.encode("utf-8"))


def _write_json(path: Path, obj: object) -> None:
    payload = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text(path, payload)


def _load_personas(source: Path):
    """Import the real Persona table without executing the rest of the app."""
    sys.path.insert(0, str(source))
    from helion.personas import PERSONAS  # noqa: WPS433 (runtime import from pinned source)
    return tuple(PERSONAS)


def _copy_source_bytes(source: Path, dest: Path) -> list[dict]:
    copied = []
    for src_rel, dest_rel in SOURCE_COPIES:
        src = source / src_rel
        target = dest / dest_rel
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            for file in sorted(p for p in src.rglob("*") if p.is_file()):
                rel = dest_rel + "/" + file.relative_to(src).as_posix()
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                payload = file.read_bytes()
                out.write_bytes(payload)
                copied.append({
                    "source": src_rel + "/" + file.relative_to(src).as_posix(),
                    "path": rel,
                    "bytes": len(payload),
                    "sha256": sha256_bytes(payload),
                })
        else:
            if not src.is_file():
                raise SystemExit(f"SOURCE_FILE_MISSING:{src_rel}")
            payload = src.read_bytes()
            _write_bytes(target, payload)
            copied.append({
                "source": src_rel,
                "path": dest_rel,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            })
    return copied


def _persona_fixtures(source: Path, dest: Path) -> None:
    catalog = json.loads((dest / "product_payload/assets/personas_5.json").read_text(encoding="utf-8"))
    by_code = {row["id"]: row for row in catalog["personas"]}
    if set(by_code) != set(PERSONA_CODES.values()):
        raise SystemExit("PERSONA_CATALOG_CODES_DO_NOT_MATCH_RUNTIME_IDS")
    for persona in _load_personas(source):
        code = PERSONA_CODES[persona.persona_id]
        row = by_code[code]
        traits = row.get("traits") or {}
        filled = sum(1 for value in traits.values() if value is not None)
        fixture = {
            "schema": "NOX_M2_PERSONA_FIXTURE_V1",
            "status": "SOURCE_CATALOG_NOT_A_SIGNED_RUNTIME_PROFILE",
            "runtime_persona_id": persona.persona_id,
            "runtime_display_name": persona.display_name,
            "runtime_role": persona.role,
            "fictional": bool(persona.fictional),
            "traits_catalog_id": code,
            "traits_catalog_name": row.get("name"),
            "traits_catalog_role": row.get("role"),
            "traits_filled": filled,
            "traits_total": len(traits),
            "license": "PENDING",
            "consent": "PENDING",
            "revoke": "PENDING",
            "owner_signed": False,
            "approved": False,
            "signed": False,
            "portrait_bytes_in_payload": False,
            "source_files": ["helion/personas.py", "assets/personas_5.json"],
            "note": "Identity text is copied from the pinned source. Consent, license, and revoke stay unsigned.",
        }
        _write_json(dest / f"fixtures/personas/{persona.persona_id}.json", fixture)


def _rights_index(dest: Path) -> None:
    csv_path = dest / "fixtures/rights/media_source_inventory_20261020.csv"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts: dict[str, int] = {}
    projected = []
    for row in rows:
        status = row.get("rights_status") or ""
        counts[status] = counts.get(status, 0) + 1
        projected.append({
            "archive_path": row.get("archive_path") or "",
            "bytes": int(row["bytes"]) if (row.get("bytes") or "").isdigit() else row.get("bytes"),
            "disposition": row.get("disposition") or "",
            "lifecycle_status": row.get("lifecycle_status") or "",
            "rights_status": status,
            "sha256": row.get("sha256") or "",
            "source_name": row.get("source_name") or "",
        })
    cleared = counts.get("CLEARED", 0) + counts.get("APPROVED", 0)
    _write_json(dest / "fixtures/rights/media_rights_index.json", {
        "schema": "NOX_M2_MEDIA_RIGHTS_INDEX_V1",
        "status": "SOURCE_RIGHTS_NOT_REVERIFIED",
        "source_csv": "rights/media_source_inventory_20261020.csv",
        "source_csv_sha256": sha256_file(csv_path),
        "row_count": len(projected),
        "rights_cleared_count": cleared,
        "rights_status_counts": counts,
        "rows": projected,
        "note": "Projected from docs/media_source_inventory_20261020.csv. No rights row was marked cleared.",
    })


def _templates(dest: Path) -> None:
    model = (dest / "product_payload/model_config.example.json").read_bytes()
    _write_bytes(dest / "fixtures/model_config.json", model)
    _write_json(dest / "fixtures/consent_receipt.template.json", {
        "schema": "NOX_M2_CONSENT_RECEIPT_TEMPLATE_V1",
        "status": "TEMPLATE",
        "owner_signed": False,
        "approved": False,
        "signed": False,
        "signed_by": None,
        "signature": None,
        "note": "Owner-only. This template does not sign or approve on the owner's behalf.",
    })
    _write_json(dest / "fixtures/license_notice.template.json", {
        "schema": "NOX_M2_LICENSE_NOTICE_TEMPLATE_V1",
        "status": "NO_BUNDLED_MODEL_LICENSE",
        "license_id": None,
        "owner_license_acknowledged": False,
        "signed": False,
        "approved": False,
        "note": "The pinned source has no owner-acknowledged base-model license. Research scorers are not a substitute.",
    })
    _write_json(dest / "fixtures/expected/product_bytes_absent.expected.json", {
        "schema": "NOX_M2_EXPECTED_V1",
        "asserts_valid": False,
        "reason": "product_bytes_absent",
        "must_be_absent_kinds": list(ABSENT_PRODUCT_KINDS),
        "qwen_layer_sha256_not_present": QWEN_LAYER_SHA256,
        "note": "Treating the empty Qwen slot or the research scorers as a base model must fail.",
    })
    _write_json(dest / "fixtures/expected/fake_rights_rows_forbidden.expected.json", {
        "schema": "NOX_M2_EXPECTED_V1",
        "asserts_valid": False,
        "reason": "fake_rights_rows_forbidden",
        "rights_cleared_must_equal": 0,
        "row_count": 173,
    })
    _write_json(dest / "fixtures/expected/exe_in_kit_forbidden.expected.json", {
        "schema": "NOX_M2_EXPECTED_V1",
        "asserts_valid": False,
        "reason": "exe_in_kit_forbidden",
        "forbidden_name": REFERENCE_EXE_NAME,
        "forbidden_sha256": REFERENCE_EXE_SHA256,
        "forbidden_bytes": REFERENCE_EXE_BYTES,
    })
    _write_json(dest / "fixtures/expected/owner_ack_unsigned.expected.json", {
        "schema": "NOX_M2_EXPECTED_V1",
        "asserts_valid": False,
        "reason": "owner_ack_must_stay_unsigned",
        "signed_must_be": False,
        "approved_must_be": False,
    })


def _app_import_manifest(dest: Path, copied: list[dict]) -> None:
    files = []
    weights_dir = dest / "product_payload/weights"
    optimizer_named_but_absent = []
    staging = json.loads((weights_dir / "STAGING_MANIFEST.json").read_text(encoding="utf-8"))
    present_names = {path.name for path in weights_dir.iterdir() if path.is_file()}
    for entry in staging.get("models", {}).values():
        for key in ("optimizer_state",):
            name = entry.get(key)
            if name and name not in present_names:
                optimizer_named_but_absent.append(name)
    for path in sorted(p for p in (dest / "product_payload").rglob("*") if p.is_file()):
        rel = path.relative_to(dest / "product_payload").as_posix()
        if rel in {MARKER_NAME, "app_import_manifest.json", "GATE_HOLD.json", "README.md"}:
            continue
        if rel.startswith("weights/") and path.suffix == ".safetensors":
            role = "research_scorer"
            loader = "helion.ai_weights.nox_weights_bridge.VerifiedWeights.load"
        elif rel == "weights/STAGING_MANIFEST.json":
            role = "research_scorer_manifest"
            loader = "helion.ai_weights.nox_weights_bridge.VerifiedWeights.load"
        elif rel == "weights/MODEL_FEATURE_CONTRACT.json":
            role = "research_scorer_contract"
            loader = "helion.ai_weights.nox_weights_bridge.VerifiedWeights.load"
        elif rel == "helion/data/menu_v2_full_catalog.json":
            role = "menu_catalog"
            loader = "helion.g3_menu_provenance.load_pinned_menu_source"
        elif rel == "helion/data/traits_seed_64.json":
            role = "trait_seed_catalog"
            loader = "json.load; schema nox_helion.persona_trait_seed.v1"
        elif rel == "assets/personas_5.json":
            role = "persona_trait_catalog"
            loader = "helion.s03_trait_engine.TraitStore.seed reads personas_5.json"
        elif rel == "assets/asset_manifest.json":
            role = "static_asset_manifest"
            loader = "helion.approved_assets inventory"
        elif rel == "model_config.example.json":
            role = "unbound_model_config_example"
            loader = "helion.first_release.load_model_config"
        else:
            role = "source_copy"
            loader = "sha256"
        files.append({
            "path": rel,
            "role": role,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "app_loader": loader,
            "kind_claim": "NOT_A_FIRST_RUN_PRODUCT_KIND",
        })
    _write_json(dest / "product_payload/app_import_manifest.json", {
        "schema": "NOX_M2_APP_IMPORT_MANIFEST_V1",
        "schema_version": 1,
        "version": VERSION,
        "product_acceptance": "0/1",
        "live_ai": False,
        "online": False,
        "files": files,
        "optimizer_state_named_but_absent": sorted(set(optimizer_named_but_absent)),
        "source_copies": copied,
        "note": "schema_version 1 is an import inventory. It is not a first-run product_payload_gate pass: file roles are not base_model, tokenizer, adapter, rag_index, or cultural_index.",
    })


def _gate_hold(dest: Path) -> None:
    _write_json(dest / "product_payload/GATE_HOLD.json", {
        "schema": "NOX_M2_FIRST_RUN_GATE_HOLD_V1",
        "status": "HOLD",
        "reason": "REQUIRED_PRODUCT_KINDS_NOT_IN_REPOSITORY",
        "missing_kinds": list(ABSENT_PRODUCT_KINDS),
        "qwen_layer": {
            "model_tag": QWEN_MODEL_TAG,
            "layer_sha256": QWEN_LAYER_SHA256,
            "layer_size_bytes": QWEN_LAYER_BYTES,
            "present": False,
            "note": "Prior checkpoints store this layer as Drive parts. Those bytes are not in this repository and were not fabricated.",
        },
        "research_scorers_are_not_a_base_model": True,
        "native_model_load": "NOT_RUN",
        "live_ai": False,
        "online": False,
        "product_acceptance": "0/1",
        "owner_signed": False,
        "approved": False,
    })


def _readmes(dest: Path) -> None:
    _write_text(dest / "product_payload/README.md", """# product_payload (M2.0-PP)

Real bytes copied from the pinned PRE-PRE source snapshot.

Included and loaded by the app's own code:
- `weights/` — seven research scorers (`VerifiedWeights.load`). They are numeric candidate scorers, not a language model and not a LoRA adapter.
- `helion/data/menu_v2_full_catalog.json` — menu catalog (`load_pinned_menu_source`).
- `helion/data/traits_seed_64.json` — trait seed catalog shipped in the candidate data path.
- `assets/personas_5.json` and `assets/asset_manifest.json` — source catalogs. Pixel files stay in the source `assets/` tree and are not duplicated here.
- `model_config.example.json` — the unbound config the desktop entrypoint accepts (`models` is empty).

Not included, because the bytes are not in this repository:
- Qwen layer `c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515` (397,807,936 bytes)
- tokenizer, adapter, RAG index, cultural index
- an owner-signed license or consent

`GATE_HOLD.json` records that hold. This directory is not product acceptance.
""")
    _write_text(dest / "fixtures/README.md", """# fixtures (M2.0-PP)

Fixtures match what the pinned app actually reads.

- `model_config.json` is a byte copy of `model_config.example.json`. `load_model_config` accepts it. No core is bound, so it is not a live model config.
- `personas/persona.*.json` are the five runtime Persona IDs from `helion/personas.py`, joined to `assets/personas_5.json`. License, consent, and revoke stay PENDING. Nothing is signed.
- `rights/media_source_inventory_20261020.csv` is the source inventory (173 rows). Every `rights_status` is `SOURCE_RIGHTS_NOT_REVERIFIED`.
- `expected/` are negative checks: missing product bytes, invented cleared rights, the reference EXE, and a signed owner ACK must all fail.

Owner-only ticks stay unsigned.
""")
    _write_text(dest / "VERSION.txt",
                "name=NOX_HELION_M2_0_PAYLOAD\n"
                f"version={VERSION}\n"
                "channel=pre-pre-candidate\n"
                f"reference_exe_name={REFERENCE_EXE_NAME}\n"
                f"reference_exe_sha256={REFERENCE_EXE_SHA256}\n"
                f"reference_exe_bytes={REFERENCE_EXE_BYTES}\n"
                f"reference_source_commit={REFERENCE_SOURCE_COMMIT}\n"
                "reference_exe_touched=false\n")
    _write_text(dest / "product_payload" / MARKER_NAME, MARKER_TEXT)


def _smoke_list(dest: Path) -> None:
    entries = []
    for path in sorted(p for p in dest.rglob("*") if p.is_file()):
        rel = path.relative_to(dest).as_posix()
        if rel in {"M2_PAYLOAD_MANIFEST.json", "fixtures/smoke_import_list.json"}:
            continue
        entries.append({
            "rel_path": rel,
            "status": "PRESENT",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    for kind in ABSENT_PRODUCT_KINDS:
        entries.append({"rel_path": f"product_payload/missing/{kind}", "status": "ABSENT", "kind": kind})
    entries.append({
        "rel_path": "product_payload/models/qwen2.5-0.5b-instruct-q4_K_M/",
        "status": "ABSENT",
        "sha256_not_present": QWEN_LAYER_SHA256,
        "bytes_not_present": QWEN_LAYER_BYTES,
    })
    _write_json(dest / "fixtures/smoke_import_list.json", {
        "schema": "NOX_M2_SMOKE_IMPORT_LIST_V1",
        "version": VERSION,
        "bound_reference_exe_sha256": REFERENCE_EXE_SHA256,
        "reference_exe_included": False,
        "entries": entries,
    })


def _top_manifest(dest: Path) -> dict:
    files = []
    for path in sorted(p for p in dest.rglob("*") if p.is_file()):
        rel = path.relative_to(dest).as_posix()
        if rel == "M2_PAYLOAD_MANIFEST.json":
            continue
        files.append({
            "path": rel,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    manifest = {
        "schema": "NOX_M2_PAYLOAD_MANIFEST_V1",
        "version": VERSION,
        "product_acceptance": "0/1",
        "live_ai": False,
        "online": False,
        "owner_signed": False,
        "approved": False,
        "reference_exe_included": False,
        "reference_exe_sha256": REFERENCE_EXE_SHA256,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    _write_json(dest / "M2_PAYLOAD_MANIFEST.json", manifest)
    return manifest


def assemble(source: Path, dest: Path) -> dict:
    source = source.resolve()
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    copied = _copy_source_bytes(source, dest)
    _persona_fixtures(source, dest)
    _rights_index(dest)
    _templates(dest)
    _gate_hold(dest)
    _readmes(dest)
    _app_import_manifest(dest, copied)
    _smoke_list(dest)
    return _top_manifest(dest)


def check(source: Path, dest: Path) -> None:
    """Rebuild in a temp directory and require byte-identical committed outputs."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="nox-m2-check-") as tmp:
        fresh = Path(tmp) / "m2"
        assemble(source, fresh)
        fresh_files = {path.relative_to(fresh).as_posix(): path.read_bytes() for path in fresh.rglob("*") if path.is_file()}
        have_files = {path.relative_to(dest).as_posix(): path.read_bytes() for path in dest.rglob("*") if path.is_file()}
    missing = sorted(set(fresh_files) - set(have_files))
    extra = sorted(set(have_files) - set(fresh_files))
    changed = sorted(rel for rel in set(fresh_files) & set(have_files) if fresh_files[rel] != have_files[rel])
    if missing or extra or changed:
        raise SystemExit(
            "M2_PAYLOAD_DRIFT missing={0} extra={1} changed={2}".format(missing, extra, changed)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dest", type=Path, default=DEFAULT_PAYLOAD_ROOT)
    parser.add_argument("--check", action="store_true", help="Fail if dest is not a fresh assemble of source")
    args = parser.parse_args(argv)
    if args.check:
        check(args.source, args.dest)
        print(f"M2_PAYLOAD_CHECK_OK {args.dest}")
        return 0
    manifest = assemble(args.source, args.dest)
    print(f"M2_PAYLOAD_ASSEMBLED files={manifest['file_count']} bytes={manifest['total_bytes']} dest={args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
