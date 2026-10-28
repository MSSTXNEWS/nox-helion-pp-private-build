"""E06 R09 additive source-only security gate for PACK01 JSON payload size.

Owner: E06 security QA. No owner file/host/DB/EXE modifications.
Pinned PR27 native_bridge.py Git blob SHA1 486e4d29a2f4d859a2923122706657915da011aa.
Run: python g3_02_r09_utf8_payload_budget_gate.py --self-test
Optional exact-owner reproduction: --owner-source /path/to/PR27/native_bridge.py
This candidate does not fix the owner dispatcher until E02/E06 approve integration.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

OWNER_BLOB_SHA1 = "486e4d29a2f4d859a2923122706657915da011aa"
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024


class PayloadDenied(ValueError):
    """Fail closed for invalid or oversized JSON data before owner execution."""


def utf8_payload_gate(payload: object) -> bytes:
    """Candidate E06 validation, NOT a second native dispatcher.

    Byte count is calculated on the actual JSON serialization, not on Python
    Unicode code-point count. Encoding, NaN, cycles and deep recursion fail closed.
    The production owner should also enforce a raw ingress-size limit.
    """
    if type(payload) is not dict:
        raise PayloadDenied("JSON object required")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
        raise PayloadDenied("Invalid JSON payload") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise PayloadDenied("UTF-8 payload exceeds 2 MiB")
    return encoded


def old_character_count_accepts(payload: dict) -> bool:
    """Pinned PR27 source expression, reconstructed solely for RED regression."""
    return len(json.dumps(payload, ensure_ascii=False)) <= MAX_PAYLOAD_BYTES


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def reproduce_on_exact_owner(source_path: Path) -> str:
    """Optional REAL owner-source reproduction. Refuse a different preimage."""
    data = source_path.read_bytes()
    actual = git_blob_sha1(data)
    if actual != OWNER_BLOB_SHA1:
        return f"HOLD_OWNER_PREIMAGE_MISMATCH expected={OWNER_BLOB_SHA1} actual={actual}"
    source = data.decode("utf-8", "strict")
    if "len(json.dumps(payload,ensure_ascii=False))" not in source.replace(" ", ""):
        return "HOLD_SOURCE_EXPRESSION_CHANGED"
    name = "nox_pack01_e06_r09_exact_owner"
    spec = importlib.util.spec_from_file_location(name, source_path)
    if spec is None or spec.loader is None:
        return "HOLD_OWNER_IMPORT_UNAVAILABLE"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    catalog = {
        "version": "NOX-INTEGRATION-PACK-01",
        "actions": [
            {"taskId": f"NIP01-{i:02d}", "routeId": route, "owner": 2, "risk": "safe"}
            for i, route in enumerate(sorted(module.ALLOWED_ROUTES), 1)
        ],
    }
    host = module.NoxPackHost(catalog)
    host.bind("helion.chat", module.BoundPort(lambda scope, args: "OWNER_CALLED", lambda: True, "E06_SYNTHETIC_ONLY", 2))
    scope = module.NativeSession("test-tenant", "test-principal", "test-chat", frozenset({"helion.chat"}))
    oversized = {"text": "界" * 800_000}
    if old_character_count_accepts(oversized) is not True:
        return "HOLD_UNEXPECTED_OLD_THRESHOLD"
    if len(json.dumps(oversized, ensure_ascii=False).encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return "HOLD_UNEXPECTED_BYTE_THRESHOLD"
    try:
        outcome = host.execute("helion.chat", oversized, scope)
    except module.HostDenied:
        return "OWNER_FIX_PRESENT_OVERSIZE_DENIED"
    return "RED_OWNER_OVERSIZE_ACCEPTED" if outcome == "OWNER_CALLED" else "HOLD_UNEXPECTED_OWNER_RESULT"


class UTF8BudgetRegression(unittest.TestCase):
    def test_ascii_small_pass(self):
        self.assertTrue(utf8_payload_gate({"text": "hello"}))

    def test_multibyte_codepoint_gap_reproduced_synthetically(self):
        value = {"text": "界" * 800_000}
        self.assertTrue(old_character_count_accepts(value))
        self.assertGreater(len(json.dumps(value, ensure_ascii=False).encode("utf-8")), MAX_PAYLOAD_BYTES)
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate(value)

    def test_oversize_ascii_rejected(self):
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate({"text": "a" * (MAX_PAYLOAD_BYTES + 1)})

    def test_non_object_rejected(self):
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate(["not", "object"])

    def test_nan_rejected(self):
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate({"float": float("nan")})

    def test_surrogate_rejected(self):
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate({"text": "\ud800"})

    def test_cycle_rejected(self):
        value: dict = {}
        value["self"] = value
        with self.assertRaises(PayloadDenied):
            utf8_payload_gate(value)

    def test_byte_boundary(self):
        self.assertEqual(len(utf8_payload_gate({"text": "界" * 2})), len(json.dumps({"text": "界" * 2}, ensure_ascii=False).encode("utf-8")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--owner-source", type=Path)
    args = parser.parse_args()
    if args.self_test or args.owner_source is None:
        ok = unittest.main(argv=[sys.argv[0]], exit=False, verbosity=2).result.wasSuccessful()
        if not ok:
            sys.exit(1)
    if args.owner_source is not None:
        status = reproduce_on_exact_owner(args.owner_source)
        print(status)
        if status.startswith("HOLD_"):
            sys.exit(2)
