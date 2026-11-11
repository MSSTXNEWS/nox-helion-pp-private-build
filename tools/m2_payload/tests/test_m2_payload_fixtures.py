"""M2.0 payload and fixture checks. Requires the pinned source tree."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from assemble_m2_payload import assemble, check  # noqa: E402
from m2_common import REFERENCE_EXE_NAME, REFERENCE_EXE_SHA256, sha256_file  # noqa: E402
from m2_import_smoke import run_smoke  # noqa: E402


def _source() -> Path:
    env = os.environ.get("NOX_SOURCE_ROOT")
    if env:
        return Path(env)
    cached = Path("/tmp/noxsrc/tree")
    if (cached / "helion" / "personas.py").is_file():
        return cached
    raise unittest.SkipTest("pinned source tree is not extracted")


class M2PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _source()
        cls.payload = REPO / "build_inputs" / "m2"

    def test_committed_tree_matches_a_fresh_assemble(self):
        check(self.source, self.payload)

    def test_import_smoke_passes_and_gate_holds(self):
        report = run_smoke(source=self.source, payload_root=self.payload)
        self.assertEqual(report["import_smoke"], "PASS", report["errors"])
        self.assertEqual(report["first_run_product_gate"], "HOLD")
        self.assertIn("KIND_INVALID", report["first_run_product_gate_reason"])
        self.assertFalse(report["owner_ack"]["signed"])
        self.assertFalse(report["owner_ack"]["approved"])
        self.assertFalse(report["live_ai"])
        self.assertFalse(report["online"])
        self.assertEqual(report["product_acceptance"], "0/1")
        self.assertFalse(report["reference_exe_touched"])
        self.assertEqual(len(report["persona_ids"]), 5)
        self.assertTrue(all(item["ok"] for item in report["checks"]))

    def test_reference_exe_is_not_in_the_payload(self):
        for path in self.payload.rglob("*"):
            if not path.is_file():
                continue
            self.assertNotEqual(path.name, REFERENCE_EXE_NAME)
            if path.stat().st_size == 79088677:
                self.assertNotEqual(sha256_file(path), REFERENCE_EXE_SHA256)

    def test_research_scorers_are_not_labeled_as_a_base_model(self):
        manifest = json.loads((self.payload / "product_payload" / "app_import_manifest.json").read_text(encoding="utf-8"))
        roles = {item["path"]: item["role"] for item in manifest["files"]}
        self.assertEqual(roles["weights/01_truthful_memory.safetensors"], "research_scorer")
        self.assertTrue(manifest["optimizer_state_named_but_absent"])
        hold = json.loads((self.payload / "product_payload" / "GATE_HOLD.json").read_text(encoding="utf-8"))
        self.assertFalse(hold["qwen_layer"]["present"])
        self.assertIn("base_model", hold["missing_kinds"])

    def test_rights_index_does_not_clear_any_row(self):
        index = json.loads((self.payload / "fixtures" / "rights" / "media_rights_index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["row_count"], 173)
        self.assertEqual(index["rights_cleared_count"], 0)

    def test_overlay_renames_the_candidate_and_keeps_the_reference_name_out(self):
        """The private build overlays the sprint script after the pinned tree check."""
        script = (REPO / "private_build.ps1").read_text(encoding="utf-8")
        self.assertIn("Name='NOX_HELION_M2_0_PAYLOAD'", script)
        self.assertIn("Name='NOX_HELION_M2_0_BACKGROUND'", script)
        self.assertIn("REFERENCE_EXE_EMITTED", script)
        self.assertIn(REFERENCE_EXE_SHA256, script)
        self.assertIn("M2_OVERLAY_REFERENCE_NAME_STILL_PRESENT", script)

    def test_rebuild_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a"
            second = Path(tmp) / "b"
            assemble(self.source, first)
            assemble(self.source, second)
            files_a = sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file())
            files_b = sorted(p.relative_to(second).as_posix() for p in second.rglob("*") if p.is_file())
            self.assertEqual(files_a, files_b)
            for rel in files_a:
                self.assertEqual((first / rel).read_bytes(), (second / rel).read_bytes(), rel)


if __name__ == "__main__":
    unittest.main()
