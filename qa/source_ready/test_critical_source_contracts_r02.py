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

    def test_pack02_source_50_candidates_are_not_mistaken_for_exe_acceptance(self):
        # SOURCE_READY must not depend on a future EXE (circular gate).
        # Assert 50 source tasks exist, but explicitly preserve NativeExe=NO
        # as a separate release gate, not a source-code failure.
        rows = list(csv.DictReader(io.StringIO(
            source("proposals/NOX-PACK02-50/acceptance-ledger.csv"))))
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({r["RouteID"] for r in rows}), 50)
        self.assertTrue(all(r["State"] == "SOURCE_IMPLEMENTED" for r in rows))
        self.assertTrue(all(r["NativeExe"] == "NO" for r in rows))

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

    def test_e06_onehost_final_source_must_not_be_diagnostic_only(self):
        # A successful diagnostic bridge is insufficient for SOURCE_READY.
        # This is an intentional RED integration gate until owner #1 binds
        # actual P02/P03/P04/P05 owners to the original single host.
        builder = source("coordination/e06/build_onehost_installer.ps1")
        bridge = source("coordination/e06/OriginalPythonDiagnosticBridge.cs")
        self.assertIn("onehost_p02_p04.py",
                      source("azure-pipelines-nox-v16.yml"))
        self.assertNotIn("ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE", builder)
        self.assertNotIn('--diagnose', bridge,
                         "Final native host is still the original read-only diagnostic")

    def test_original_p02_atomic_binding_rollback_preserved(self):
        text = source("Packages/P02/worker-python/p02_owner_route_ports.py")
        self.assertIn("def register_with_existing_pack01", text)
        self.assertIn("ports.pop(route, None)", text)
        self.assertIn("if ports.get(route) is port", text)

    def test_e07_handoff_must_have_one_seal_only(self):
        text = source("coordination/e06/Emit-E07ImmutableHandoff.ps1")
        self.assertEqual(text.count("E07_BUILDID_SEALED"), 1)
        self.assertIn("FileMode]::CreateNew", text)

    def test_wow_200_ids_are_complete_without_false_runtime_acceptance(self):
        # Catalog inventory is necessary source evidence but never E07 proof.
        catalog_ranges = (
            ("integrations/wow200/proposals/NOX-WOW51-100/catalog.mjs", 51, 100),
            ("integrations/wow200/proposals/NOX-WOW101-150/catalog.mjs", 101, 150),
            ("integrations/wow200/proposals/NOX-WOW151-200/catalog.mjs", 151, 200),
        )
        all_ids = []
        for path, start, end in catalog_ranges:
            ids = [int(x) for x in re.findall(r'"id"\s*:\s*(\d+)', source(path))]
            self.assertEqual(ids, list(range(start, end + 1)), path)
            all_ids.extend(ids)
        self.assertEqual(len(all_ids), 150)
        self.assertEqual(len(set(all_ids)), 150)
        stager = source("integrations/wow200/stage_wow200.py")
        self.assertIn('"complete_200_runtime_verified":False', stager,
                      "Catalog count cannot be promoted to Windows runtime PASS")


if __name__ == "__main__":
    unittest.main()
