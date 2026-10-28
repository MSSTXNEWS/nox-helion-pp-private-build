"""Independent fail-closed NOX V16 §46 SOURCE blocker gates.

Uses only the exact Git working tree; never writes owner state. Green tests are
source-contract evidence, not SOURCE_READY PASS or Windows acceptance.

Run from repository root:
  python -m unittest discover -s qa/source_ready -p 'test_critical_source_contracts_r02.py' -v
"""
from pathlib import Path
import csv
import io
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    f = ROOT / path
    if not f.is_file() or f.is_symlink():
        raise AssertionError("OWNER_SOURCE_MISSING_OR_SYMLINK: " + path)
    return f.read_text("utf-8")


class SourceReadyCriticalGates(unittest.TestCase):
    def test_pack01_has_fixed_50_unique_routes(self):
        data = json.loads(source("proposals/NOX-PACK01-50/catalog.json"))
        routes = [item["routeId"] for item in data["actions"]]
        self.assertEqual(len(routes), 50)
        self.assertEqual(len(set(routes)), 50)

    def test_host50_all_native_binding_receipts_must_be_real(self):
        data = json.loads(source("coordination/e06_host50/CURRENT_50_TASK_LEDGER.json"))
        self.assertEqual(len(data["rows"]), 50)
        self.assertEqual(data["countSourceBound"] + data["countHold"], 50)
        self.assertEqual(data["countHold"], 0, "HOST50 has unresolved source route owners")
        self.assertEqual(data["capabilitiesVerified"], 50, "Native owners not evidenced")
        self.assertEqual(data["integrated"], 50, "Live native 50-route binding missing")

    def test_pack01_native_routes_require_bound_owner_receipts(self):
        rows = list(csv.DictReader(io.StringIO(
            source("proposals/NOX-PACK01-50/acceptance-ledger.csv"))))
        self.assertEqual(len(rows), 50)
        missing = [r["TaskID"] for r in rows if r["NativeHost"] != "PASS"]
        self.assertFalse(missing, "Missing PACK01 native host receipts: " + ",".join(missing))

    def test_pack02_native_bindings_must_be_proven(self):
        rows = list(csv.DictReader(io.StringIO(
            source("proposals/NOX-PACK02-50/acceptance-ledger.csv"))))
        self.assertEqual(len(rows), 50)
        missing = [r["TaskID"] for r in rows if r["NativeExe"] != "YES"]
        self.assertFalse(missing, "PACK02 candidate-only native paths: " + ",".join(missing))

    def test_p04_rag_rejects_ambiguous_disk_json(self):
        text = source("Packages/P04/rag_python_compat.py")
        start = text.index("    def _read(self)")
        end = text.index("        if (not isinstance(data, dict)", start)
        reader = text[start:end]
        self.assertRegex(reader, r"object_pairs_hook|_reject_duplicate")
        self.assertRegex(reader, r"parse_constant|_reject_nonfinite")
        self.assertRegex(reader, r"parse_float|_finite_json")
        self.assertNotIn("data = json.loads(body)", reader)

    def test_p05_cache_scopes_provider_and_endpoint(self):
        text = source("Packages/P05/Space/SpaceFeedClient.cs")
        self.assertNotIn("_cache.TryGetValue(id, out var old)", text,
                         "id-only cache can reuse another provider/URL")
        self.assertNotIn("_cache[id] = snapshot", text,
                         "id-only cache destroys source provenance")

    def test_original_p02_atomic_binding_rollback_preserved(self):
        text = source("Packages/P02/worker-python/p02_owner_route_ports.py")
        self.assertIn("def register_with_existing_pack01", text)
        self.assertIn("ports.pop(route, None)", text)
        self.assertIn("if ports.get(route) is port", text)

    def test_e07_handoff_must_have_one_seal_only(self):
        text = source("coordination/e06/Emit-E07ImmutableHandoff.ps1")
        self.assertEqual(text.count("E07_BUILDID_SEALED"), 1)
        self.assertIn("FileMode]::CreateNew", text)

    def test_wow_200_runtime_verification_must_be_evidenced(self):
        text = source("integrations/wow200/stage_wow200.py")
        self.assertNotIn('"complete_200_runtime_verified":False', text,
                         "WOW200 source stager itself records runtime 200 acceptance as false")


if __name__ == "__main__":
    unittest.main()
