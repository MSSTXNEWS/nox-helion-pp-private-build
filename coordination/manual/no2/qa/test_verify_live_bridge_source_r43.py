"""Synthetic regression for R43 T08 live-bridge classifier. No Windows claims."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).with_name("verify_live_bridge_source_r43.py")
spec = importlib.util.spec_from_file_location("live_gate", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

BASE = {
    "builder": "# safe builder\n$receipt=@{one_visible_host=$true;native_bridge_scope='ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE';release_accepted=$false}\n",
    "diagnostic_bridge": 'class Bridge { void Run() { Arguments = "--diagnose"; var r = new { diagnosticOnly = true }; }}\n',
    "native_ingress": "class NativeIngress:\n    def handle(self, encoded: bytes) -> bytes:\n        return b''\n",
}


class BridgeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write()

    def write(self, **overrides):
        content = BASE | overrides
        for key, value in content.items():
            p = self.root / m.FILES[key]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value, encoding="utf-8")

    def test_diagno_only_never_passes_as_live(self):
        data = m.audit(self.root)
        self.assertIn("BUILDER_DECLARES_DIAGNOSTIC_ONLY_NOT_LIVE", data["blockers"])
        self.assertIn("DIAGNOSTIC_BRIDGE_NOT_LIVE_FUNCTION_PROOF", data["blockers"])

    def test_native_ingress_exists_not_equivalent_to_wired_exe(self):
        data = m.audit(self.root)
        self.assertTrue(data["observations"]["nativeIngressSourceExists"])
        self.assertFalse(data["sourceReady"])

    def test_unknown_scope_is_not_auto_accepted(self):
        self.write(builder="native_bridge_scope='LIVE_OWNER_CANDIDATE'\n", diagnostic_bridge="class Bridge {}\n")
        data = m.audit(self.root)
        self.assertEqual(data["blockers"], ["LIVE_NATIVE_WPF_IPC_OWNER_RECEIPT_NOT_VERIFIED"])

    def test_repeated_scope_is_rejected(self):
        self.write(builder="native_bridge_scope='LIVE'\nnative_bridge_scope='LIVE'\n")
        self.assertIn("EXACTLY_ONE_BUILDER_BRIDGE_SCOPE_REQUIRED", m.audit(self.root)["blockers"])

    def test_missing_source_holds(self):
        (self.root / m.FILES["native_ingress"]).unlink()
        self.assertTrue(any("REQUIRED_SOURCE_MISSING" in b for b in m.audit(self.root)["blockers"]))

    def test_symlinked_ancestor_is_rejected(self):
        path = self.root / m.FILES["native_ingress"]
        path.unlink()
        path.symlink_to(self.root / m.FILES["builder"])
        self.assertTrue(any("SYMLINK" in b for b in m.audit(self.root)["blockers"]))

    def test_invalid_utf8_rejected(self):
        (self.root / m.FILES["builder"]).write_bytes(b"\xff\xfe")
        self.assertTrue(any("INVALID_UTF8" in b for b in m.audit(self.root)["blockers"]))

    def test_missing_ingress_contract_rejected(self):
        self.write(native_ingress="class NativeIngress:\n    pass\n")
        self.assertIn("EXISTING_NATIVE_INGRESS_SOURCE_NOT_FOUND", m.audit(self.root)["blockers"])

    def test_receipt_sha256_and_status_stable(self):
        data = m.audit(self.root)
        self.assertEqual(len(data["sourceFiles"]), 3)
        self.assertTrue(all(len(x["sha256"]) == 64 for x in data["sourceFiles"]))
        self.assertFalse(data["nativeWindowsTested"])
        self.assertFalse(data["independentT08Accepted"])
        self.assertFalse(data["e07Accepted"])


if __name__ == "__main__":
    unittest.main()
