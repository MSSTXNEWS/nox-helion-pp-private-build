"""Frozen WOW V5 setup identity and fail-closed regression; never a physical E07 pass."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "coordination" / "e07" / "probe_wow_v5_five_uia_u10.py"

class WowV5FrozenSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = PROBE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.code)

    def test_exact_producer_pins(self):
        keys = {"SOURCE", "SETUP_SHA", "BYTES", "BUILDID"}
        values = {node.targets[0].id: ast.literal_eval(node.value)
                  for node in self.tree.body
                  if isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id in keys}
        self.assertEqual(values, {
            "SOURCE": "a4520e3bfffc703eb4c4689ea801608bcaacd479",
            "SETUP_SHA": "9f986c5d730e77f68d5e56acb64b7906f688a8f36d611e6d35d5993e1fcb05d1",
            "BYTES": 169603299,
            "BUILDID": "NOX-V16-e31c73097803225c1064f443"})

    def test_actual_immutable_guards_preserved(self):
        for token in ("source_receipts_729_parity_verified", "source_files",
                      "setup_sha256", "build_id", "manifest_files_checked",
                      "samevm_lifecycle_verified", "installed_file_sha_locked",
                      "return_pe_header=True", "release_accepted",
                      "evaluate(result[\"checks\"][\"installed_gui\"])",
                      "e07.lifecycle(setup,result,physical_nav=True)"):
            with self.subTest(token=token):
                self.assertIn(token, self.code)
        self.assertNotIn('"release_accepted":True', self.code)
        self.assertNotIn('"independent_e07_10_10":"PASS"', self.code)

if __name__ == "__main__":
    unittest.main()
