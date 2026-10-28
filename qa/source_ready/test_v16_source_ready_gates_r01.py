"""V16 §46 independent SOURCE_READY evidence gates on real repository files.

Intentional RED on present staged-only source is NOT a product-runtime failure.
These tests must never promote candidate source or mock output to PASS.
Run from exact pinned PR162 checkout with:
  python -m unittest discover -s qa/source_ready -p 'test_v16_source_ready_gates_r01.py' -v

TestIDs: QA-SR-P0-HOST50, QA-SR-P0-ONEHOST,
         QA-SR-P1-WOW200, QA-SR-P1-PACK02, QA-SR-P0-729.
"""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SourceReadyGates(unittest.TestCase):
    def test_host50_current_ledger_requires_all_50_native_bindings(self):
        # Source binding != installed execution. A stale "CURRENT" ledger
        # cannot supply a valid SOURCE_READY signature for NIP01-01..50.
        path = ROOT / "coordination/e06_host50/CURRENT_50_TASK_LEDGER.json"
        j = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(j["rows"]), 50)
        self.assertEqual(j["countHold"], 0, "Host50 has unreviewed owner bindings")
        self.assertEqual(j["integrated"], 50, "Require exact live owner receipts")

    def test_existing_onehost_not_diagnostic_only_for_source_ready(self):
        # Native full-source contract must be available BEFORE a release freeze.
        path = ROOT / "coordination/e06/build_onehost_installer.ps1"
        s = path.read_text(encoding="utf-8")
        self.assertNotIn(
            "native_bridge_scope='ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE'", s,
            "E06 still reports read-only diagnostic rather than live P02–P05 source bindings",
        )

    def test_wow200_has_non_mock_full_runtime_source_proof(self):
        path = ROOT / "integrations/wow200/stage_wow200.py"
        s = path.read_text(encoding="utf-8")
        self.assertNotIn(
            '"complete_200_runtime_verified":False', s,
            "WOW catalog/staging alone is not verified 200-effect runtime coverage",
        )

    def test_pack02_fifty_native_routes_are_not_just_source_candidates(self):
        path = ROOT / "proposals/NOX-PACK02-50/acceptance-ledger.csv"
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        self.assertEqual(len(rows), 50)
        unbound = [r["TaskID"] for r in rows
                   if r["NativeExe"] != "YES" or r["Accepted"] != "YES"]
        self.assertEqual(unbound, [], "NIP02 native route proofs missing: " +
                         ",".join(unbound))

    def test_real_three_part_729_source_lock_in_exact_checkout(self):
        # This runs the ORIGINAL verifier, not a copied parser, and never
        # extracts/overwrites any source file or receipt.
        verifier = ROOT / "coordination/e06/verify_original_729_source.py"
        self.assertTrue(verifier.is_file())
        for part in ("source_00.part", "source_01.part", "source_02.part"):
            self.assertTrue((ROOT / part).is_file(), "Original source part absent: " + part)
        with tempfile.TemporaryDirectory(prefix="nox-v16-source-qa-") as td:
            out = Path(td) / "verified729.json"
            run = subprocess.run(
                [sys.executable, str(verifier), "--parts-dir", str(ROOT),
                 "--out", str(out), "--run-id", "NOX-V16-SOURCE-QA-R01"],
                cwd=ROOT, text=True, capture_output=True, timeout=240,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stdout[-1200:] + run.stderr[-1200:])
            receipt = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(receipt["fileCount"], 729)
            self.assertEqual(
                receipt["combinedZip"]["sha256"],
                "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a",
            )
            self.assertEqual(len(receipt["files"]), 729)
            self.assertTrue(all(len(row["sha256"]) == 64 for row in receipt["files"]))


if __name__ == "__main__":
    unittest.main()
