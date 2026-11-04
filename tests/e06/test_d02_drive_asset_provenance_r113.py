"""Source-only NOX EXPRESS approved D02 raw-art provenance crosscheck.

This verifies that an immutable, independently binary-rehashed Drive receipt
matches the ORIGINAL D02 Windows stager, existing BOOST cache pins and approved
UI hashes. It does NOT download files, replace trusted SourceLock, simulate a
Windows install, or count optional screens as a mandatory E06 gate.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "coordination/express/D02_APPROVED_SOURCE_PROVENANCE_20261104.json"
STAGER = ROOT / "integrations/wow200/stage_wow200.py"
CACHE = ROOT / "coordination/express/BOOST_V4_CACHE_REUSE_R63.json"
APPROVED = ROOT / "ui/approved/SHA256.txt"
REQUIRED = frozenset({"home.png", "menu.png", "core01.png", "menu_sections.png"})
OPTIONAL = "home-max-motion.png"
PNG_MAGIC = "89504e470d0a1a0a"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


def pinned_stage_d02():
    tree = ast.parse(STAGER.read_text(encoding="utf-8"), filename=str(STAGER))
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "D02"
            for target in stmt.targets
        ):
            return ast.literal_eval(stmt.value)
    raise AssertionError("NOX_D02_STAGE_PIN_MISSING_HOLD")


def validate_receipt(obj):
    if obj.get("schema") != "NOX_HELION_EXPRESS_D02_APPROVED_RAW_ASSET_SHA256_V1":
        raise ValueError("NOX_D02_RECEIPT_SCHEMA_HOLD")
    rows = obj.get("assets")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("NOX_D02_RECEIPT_COUNT_HOLD")
    names = [row.get("role") for row in rows]
    if len(set(names)) != 5 or set(names) != REQUIRED | {OPTIONAL}:
        raise ValueError("NOX_D02_RECEIPT_ROLES_HOLD")
    ids = [row.get("drive_file_id") for row in rows]
    if len(set(ids)) != 5 or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("NOX_D02_RECEIPT_DRIVE_ID_HOLD")
    for row in rows:
        if row.get("mandatory") is not (row["role"] in REQUIRED):
            raise ValueError("NOX_D02_RECEIPT_GATE_SCOPE_HOLD")
        if row.get("signature_hex") != PNG_MAGIC:
            raise ValueError("NOX_D02_RECEIPT_PNG_MAGIC_HOLD")
        if not isinstance(row.get("bytes"), int) or not 1000 < row["bytes"] < 20_000_000:
            raise ValueError("NOX_D02_RECEIPT_BYTES_HOLD")
        if not isinstance(row.get("sha256"), str) or not SHA_RE.fullmatch(row["sha256"]):
            raise ValueError("NOX_D02_RECEIPT_HASH_FORMAT_HOLD")
        if row.get("source_url") != (
            "https://drive.google.com/file/d/" + row["drive_file_id"] + "/view"
        ):
            raise ValueError("NOX_D02_RECEIPT_SOURCE_URL_HOLD")
    if obj.get("method", {}).get("bytes_verified_count") != 5:
        raise ValueError("NOX_D02_RECEIPT_SOURCE_BYTES_HOLD")
    if obj.get("build_verification", {}).get("release_accepted") is not False:
        raise ValueError("NOX_D02_FALSE_RELEASE_PASS_HOLD")
    by_role = {row["role"]: row for row in rows}
    if pinned_stage_d02() != {role: by_role[role]["sha256"] for role in REQUIRED}:
        raise ValueError("NOX_D02_SOURCE_PIN_HOLD")
    return by_role


def verified_receipt():
    return validate_receipt(json.loads(RECEIPT.read_text(encoding="utf-8")))


class ApprovedD02Provenance(unittest.TestCase):
    def test_current_original_stage_all_four_sha_pins(self):
        receipt = verified_receipt()
        self.assertEqual(pinned_stage_d02(), {k: receipt[k]["sha256"] for k in REQUIRED})

    def test_cache_bytes_and_sha_are_identical_to_raw_drive_receipts(self):
        receipt = verified_receipt()
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
        rows = {x["name"]: x for x in cache["cache_files"]}
        for role in REQUIRED:
            row = receipt[role]
            item = rows[row["cache_alias"]]
            self.assertEqual(item["sha256"], row["sha256"], role)
            self.assertEqual(item["bytes"], row["bytes"], role)

    def test_approved_ui_sha_receipts_and_optional_scope(self):
        receipt = verified_receipt()
        lines = APPROVED.read_text(encoding="utf-8").splitlines()
        pins = dict(s.split() for s in lines if len(s.split()) == 2 and SHA_RE.fullmatch(s.split()[1]))
        for role in ("home.png", "menu.png", OPTIONAL):
            row = receipt[role]
            self.assertEqual(pins[row["ui_alias"]], row["sha256"], role)
        self.assertFalse(receipt[OPTIONAL]["mandatory"])
        self.assertIsNone(receipt[OPTIONAL]["cache_alias"])

    def test_tamper_fail_closed_with_no_native_or_ci_shortcut(self):
        obj = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertFalse(obj["build_verification"]["release_accepted"])
        self.assertIsNone(obj["build_verification"]["setup_sha256"])
        self.assertEqual(obj["build_verification"]["independent_E07"], "NOT_RUN_0_OF_10")
        self.assertFalse(obj["method"]["staged_windows_binary_rehashed_this_run"])
        # Negative tests must fail even before checking the original stage maps.
        for corruption, name in (
            (("assets", 1, "drive_file_id"), "NOX_D02_RECEIPT_DRIVE_ID_HOLD"),
            (("assets", 0, "bytes"), "NOX_D02_RECEIPT_BYTES_HOLD"),
            (("assets", 0, "sha256"), "NOX_D02_RECEIPT_HASH_FORMAT_HOLD"),
            (("assets", 2, "sha256_valid_but_wrong"), "NOX_D02_SOURCE_PIN_HOLD"),
        ):
            tampered = copy.deepcopy(obj)
            a, i, key = corruption
            value = (tampered[a][0]["drive_file_id"]
                     if key == "drive_file_id" else
                     -1 if key == "bytes" else
                     "0" * 64 if key == "sha256_valid_but_wrong" else "incorrect")
            tampered[a][i]["sha256" if key == "sha256_valid_but_wrong" else key] = value
            self.assertRaisesRegex(ValueError, name, validate_receipt, tampered)

if __name__ == "__main__":
    unittest.main()
