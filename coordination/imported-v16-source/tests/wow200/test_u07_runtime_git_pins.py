"""Fail-closed regression: original WOW200 runtime files are Git-blob-locked."""
from __future__ import annotations
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nox_pinned_wow_stager_u07", ROOT / "integrations/wow200/stage_wow200.py"
)
assert SPEC is not None and SPEC.loader is not None
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


class RuntimePinRegression(unittest.TestCase):
    def test_all_four_real_runtime_sources_have_exact_blobs(self):
        expected = {
            "runtime/loader.mjs", "runtime/stage.css",
            "runtime/home-scene.mjs", "runtime/home-guard.css"
        }
        self.assertEqual(set(stage.WOW_RUNTIME_BLOBS), expected)
        for rel, pin in stage.WOW_RUNTIME_BLOBS.items():
            with self.subTest(rel=rel):
                path = ROOT / "integrations/wow200" / rel
                self.assertTrue(path.is_file())
                admitted = stage.pinned_source_bytes(path, pin)
                self.assertIsNotNone(admitted)
                self.assertEqual(stage.gitsha(admitted), pin)

    def test_mutated_real_runtime_source_does_not_pass_pin(self):
        rel = "runtime/loader.mjs"
        raw = (ROOT / "integrations/wow200" / rel).read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "loader.mjs"
            changed.write_bytes(raw + b"\n// unapproved mutation\n")
            self.assertIsNone(stage.pinned_source_bytes(
                changed, stage.WOW_RUNTIME_BLOBS[rel]
            ))

    def test_stager_uses_verified_bytes_and_emits_non_release_receipt(self):
        source = (ROOT / "integrations/wow200/stage_wow200.py").read_text("utf-8")
        self.assertIn("for rel, expected in WOW_RUNTIME_BLOBS.items():", source)
        self.assertIn("pinned_content[origin]=verified", source)
        self.assertIn('"wow_runtime_git_blobs":WOW_RUNTIME_BLOBS', source)
        self.assertIn('"release_accepted":False', source)


if __name__ == "__main__":
    unittest.main()
