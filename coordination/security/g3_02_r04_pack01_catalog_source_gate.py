"""NOX V16 / E06 G3-02 R04: SOURCE-ONLY catalog provenance gate.

Owner: E06 Security (NOT P02 owner). No product integration, no installer edit.
Frozen shared baseline: 0b3a7d435be735148d64171deb9027093a89646e
Reference only: PR27 exact head be1fe05d88443e41b0d196617840508d9dd39b7d
No replacement of native_bridge.py, original ZIP, D02/Persona/WOW or app host.

The P02 NoxPackHost builds self.routes from the supplied catalog and obtains
sensitive/dangerous classifications from that object during execute(). A
downgraded catalog is therefore not a security authority. This gate accepts
only the exact byte-pinned SOURCE CANDIDATE pair; E06 must independently
validate original source_00/01/02 and explicitly wire the gate at the trusted
native host boundary before any runtime/Windows acceptance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import unittest
from dataclasses import dataclass

RUN_ID = "NOX-V16-G3-02-SEC-20261028T0933MSK-R04"
SOURCE_REF = "be1fe05d88443e41b0d196617840508d9dd39b7d"
CATALOG_PATH = "proposals/NOX-PACK01-50/catalog.json"
OWNER_PATH = "proposals/NOX-PACK01-50/native_bridge.py"
CATALOG_SHA256 = "ac7c266340e897549498b1b52f2ee74c8df6678d0e6ff02ac358a77e9537c21c"
OWNER_SHA256 = "8a9912ade9e252677b10b5981cca271afdff8467ee8c0a6fc1005bd47fed760f"
CATALOG_GIT_BLOB_SHA1 = "c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d"
OWNER_GIT_BLOB_SHA1 = "486e4d29a2f4d859a2923122706657915da011aa"
DANGEROUS_ROUTE_OWNERS = {
    "training.start": 4,
    "calls.dial": 2,
    "system.update": 1,
    "system.backup": 1,
    "system.pc_control": 1,
}
MAX_FILE_BYTES = 65536


class SecurityHold(RuntimeError):
    """Missing or mismatched trusted native source evidence: fail closed."""


@dataclass(frozen=True)
class CandidateReceipt:
    run_id: str
    owner_source_ref: str
    catalog_sha256: str
    bridge_sha256: str
    route_count: int
    state: str = "SOURCE_CANDIDATE_ONLY"
    integrated: bool = False
    windows_accepted: bool = False


def _check_exact_bytes(value: bytes, expected_sha256: str, label: str) -> None:
    if type(value) is not bytes or not 1 <= len(value) <= MAX_FILE_BYTES:
        raise SecurityHold(label + ": INVALID_RAW_SIZE_OR_TYPE")
    actual = hashlib.sha256(value).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise SecurityHold(label + ": IMMUTABLE_SHA256_MISMATCH")


def verify_candidate_pair(catalog_raw: bytes, native_bridge_raw: bytes) -> CandidateReceipt:
    """Check an immutable donor pair, NOT the original 729-file SourceLock.

    Never pass raw content or a digest from a WebView message. Input must be
    read from E06's independently proven local source. This function does not
    return a runtime-approved claim or install a privileged handler.
    """
    _check_exact_bytes(catalog_raw, CATALOG_SHA256, "PACK01_CATALOG")
    _check_exact_bytes(native_bridge_raw, OWNER_SHA256, "P02_NATIVE_BRIDGE")
    try:
        catalog = json.loads(catalog_raw.decode("utf-8", "strict"))
    except (ValueError, UnicodeError) as exc:
        raise SecurityHold("CATALOG_JSON_INVALID") from exc
    if not isinstance(catalog, dict) or catalog.get("version") != "NOX-INTEGRATION-PACK-01":
        raise SecurityHold("CATALOG_VERSION_INVALID")
    actions = catalog.get("actions")
    if not isinstance(actions, list) or len(actions) != 50:
        raise SecurityHold("CATALOG_ROUTE_COUNT_INVALID")
    ids = [entry.get("routeId") for entry in actions if isinstance(entry, dict)]
    if len(ids) != 50 or len(set(ids)) != 50:
        raise SecurityHold("CATALOG_DUPLICATE_OR_NON_OBJECT_ROUTE")
    for route, owner in DANGEROUS_ROUTE_OWNERS.items():
        matched = [entry for entry in actions if entry["routeId"] == route]
        if len(matched) != 1 or matched[0].get("risk") != "dangerous" or matched[0].get("owner") != owner:
            raise SecurityHold("CATALOG_PRIVILEGE_DOWNGRADE:" + route)
    return CandidateReceipt(
        run_id=RUN_ID,
        owner_source_ref=SOURCE_REF,
        catalog_sha256=CATALOG_SHA256,
        bridge_sha256=OWNER_SHA256,
        route_count=50,
    )


class SecurityCandidateTests(unittest.TestCase):
    """Synthetic negative tests. Real original-owner and Windows tests are HOLD."""

    def test_missing_pair_is_denied(self):
        with self.assertRaises(SecurityHold):
            verify_candidate_pair(b"", b"")

    def test_unpinned_catalog_is_denied(self):
        with self.assertRaisesRegex(SecurityHold, "IMMUTABLE_SHA256_MISMATCH"):
            verify_candidate_pair(b'{"version":"NOX-INTEGRATION-PACK-01","actions":[]}', b"x")

    def test_oversized_catalog_is_denied(self):
        with self.assertRaisesRegex(SecurityHold, "INVALID_RAW_SIZE_OR_TYPE"):
            verify_candidate_pair(b"Z" * (MAX_FILE_BYTES + 1), b"x")

    def test_nonbyte_catalog_is_denied(self):
        with self.assertRaisesRegex(SecurityHold, "INVALID_RAW_SIZE_OR_TYPE"):
            verify_candidate_pair('{"actions":[]}', b"x")  # type: ignore[arg-type]

    def test_forged_owner_cannot_admit(self):
        with self.assertRaisesRegex(SecurityHold, "IMMUTABLE_SHA256_MISMATCH"):
            _check_exact_bytes(b"def execute(): return True", OWNER_SHA256, "P02_NATIVE_BRIDGE")

    def test_frozen_candidate_never_claims_release(self):
        receipt = CandidateReceipt(RUN_ID, SOURCE_REF, CATALOG_SHA256, OWNER_SHA256, 50)
        self.assertFalse(receipt.integrated)
        self.assertFalse(receipt.windows_accepted)
        self.assertEqual(receipt.state, "SOURCE_CANDIDATE_ONLY")

    def test_critical_route_pin_has_five_distinct_routes(self):
        self.assertEqual(len(DANGEROUS_ROUTE_OWNERS), 5)
        self.assertEqual(DANGEROUS_ROUTE_OWNERS["calls.dial"], 2)
        self.assertEqual(DANGEROUS_ROUTE_OWNERS["system.pc_control"], 1)

    @unittest.skipUnless(os.environ.get("NOX_P01_CATALOG") and os.environ.get("NOX_P02_BRIDGE"),
                         "Exact PR27 byte files not present: positive owner check NOT_RUN")
    def test_positive_exact_pr27_donor_pair(self):
        with open(os.environ["NOX_P01_CATALOG"], "rb") as fc:
            cat = fc.read(MAX_FILE_BYTES + 1)
        with open(os.environ["NOX_P02_BRIDGE"], "rb") as fb:
            owner = fb.read(MAX_FILE_BYTES + 1)
        result = verify_candidate_pair(cat, owner)
        self.assertEqual(result.state, "SOURCE_CANDIDATE_ONLY")


if __name__ == "__main__":
    unittest.main()
