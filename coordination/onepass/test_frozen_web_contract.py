"""Offline tests of frozen source completeness; do not claim server PASS."""
import tempfile
from pathlib import Path
import unittest
from coordination.onepass import frozen_web_contract as audit


class FrozenSourceContractTests(unittest.TestCase):
    def test_native_registration_does_not_equal_e2e(self):
        self.assertEqual(audit.ROUTE_COUNT,92)
        self.assertEqual(audit.NATIVE_EXACT_REGISTRATION,23)
        self.assertNotEqual(audit.ROUTE_COUNT,audit.NATIVE_EXACT_REGISTRATION)
        self.assertEqual(audit.ZIP_FILES,1089)
    def test_exact_path_not_prefix_confusion(self):
        self.assertTrue(audit.find_literal("fetch('/api/status')","/api/status"))
        self.assertFalse(audit.find_literal("fetch('/api/status-extra')","/api/status"))
        self.assertTrue(audit.find_literal("api('/api/install/'+action)","/api/install/"))
    def test_client_location_is_not_server_telemetry(self):
        for r in ('/api/pc-metrics','/api/install/scan','/api/voice/transcribe'):
            self.assertTrue(audit.host_boundary(r).startswith("WINDOWS_OWNER_PC"))
        self.assertNotIn("WINDOWS",audit.host_boundary("/api/nox/status"))
    def test_source_refs_preserve_paths_and_lines(self):
        found=audit.static_refs("\nlet x=fetch('/api/nox/chat/stream');\n","/api/nox/chat/stream","nox-chat.js")
        self.assertEqual(found,[{"file":"nox-chat.js","line":2}])
    def test_unknown_zip_is_rejected_before_extract(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"WRONG.zip"
            p.write_bytes(b"this is not the real frozen web")
            with self.assertRaisesRegex(ValueError,"HOLD_FROZEN_ZIP_SHA256_CHANGED"):
                audit.analyze(p,Path(root)/"matrix.json")


if __name__=="__main__":
    unittest.main()
