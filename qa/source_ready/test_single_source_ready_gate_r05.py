"""Independent NOX V16 SOURCE_READY admission gate R05.

Run from the exact private repo working tree:
  python -m unittest discover -s qa/source_ready -p test_single_source_ready_gate_r05.py -v

Test failures are missing SOURCE evidence, NOT Windows E07 failures.
This file never writes product data, builds an EXE or starts native owners.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def file(path):
    candidate = ROOT / path
    if not candidate.is_file() or candidate.is_symlink():
        raise AssertionError("ORIGINAL_SOURCE_MISSING_OR_SYMLINK: " + path)
    return candidate


def text(path):
    return file(path).read_text(encoding="utf-8")


def git_blob(path):
    data = file(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\0" + data).hexdigest()


def wow_active_pin():
    tree = ast.parse(text("integrations/wow200/stage_wow200.py"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "OWNER1_D02_ENGINE"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("WOW_STAGE_APPROVED_OWNER_PINS_NOT_FOUND")


class SourceReadyR05(unittest.TestCase):
    def test_d02_active_owner_pin_must_match_current_source(self):
        # Confirmed RED: the real active JS is newer than the staging SHA pin.
        path = "proposals/NOX-CINEMA-FX/nox-cinema.mjs"
        expected = wow_active_pin()[path]["active_blob"]
        actual = git_blob(path)
        self.assertEqual(actual, expected,
                         "P0 D02_ENGINE_SHA_DRIFT: owner #1 must review and CAS pin")

    def test_host50_ledger_must_match_owner_binding_map(self):
        # This does not claim a specific number of missing REAL handlers.
        old = json.loads(text(
            "coordination/e06_host50/CURRENT_50_TASK_LEDGER.json"))
        owner = json.loads(text(
            "proposals/NOX-PACK01-50/owner-binding-map.json"))
        catalog = json.loads(text("proposals/NOX-PACK01-50/catalog.json"))
        self.assertEqual(len(catalog["actions"]), 50)
        by_task = {row["taskId"]: row for row in owner["routes"]}
        self.assertEqual(len(by_task), 50)
        self.assertEqual(len(old["rows"]), 50)
        inconsistent = [
            row["taskId"] for row in old["rows"]
            if (row["SOURCE"] == "CANDIDATE")
            != bool(by_task[row["taskId"]].get("sourceBinding"))
        ]
        self.assertFalse(inconsistent,
                         "P0 HOST50_LEDGER_DRIFT: " + ",".join(inconsistent))

    def test_legacy_diagnostic_bridge_cannot_count_as_full_onehost(self):
        # This is an admission EVIDENCE gate, not proof other P02/P03/P04
        # owner modules do not exist. Requires real native route binding.
        script = text("coordination/e06/build_onehost_installer.ps1")
        self.assertNotIn(
            "ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE", script,
            "P0 ONEHOST_DIAGNOSTIC_ONLY: require complete source handler admission")

    def test_original_e07_receipt_is_no_clobber(self):
        script = text("coordination/e06/Emit-E07ImmutableHandoff.ps1")
        self.assertEqual(script.count("E07_BUILDID_SEALED"), 1)
        self.assertIn("FileMode]::CreateNew", script)


if __name__ == "__main__":
    unittest.main()
