"""Verify original E06 builder pins current strict native receipt verifier."""
import hashlib, pathlib, re, unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
VERIFIER = ROOT / "coordination/e06/verify_native_receipt_json.py"

def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()

class SourcePinTests(unittest.TestCase):
    def test_live_verifier_pin(self):
        text = BUILDER.read_text(encoding="utf-8-sig")
        matches = re.findall("expectedNativeVerifierBlob='([0-9a-f]{40})'", text)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], blob_sha(VERIFIER.read_bytes()))

    def test_failclosed_native_admission(self):
        text = BUILDER.read_text(encoding="utf-8-sig")
        self.assertIn("E06_NATIVE_RECEIPT_VERIFIER_PIN_HOLD", text)
        self.assertIn("E06_NATIVE_RECEIPT_STRICT_JSON_HOLD", text)
        self.assertIn("$strictEntry.Substring(65) | ConvertFrom-Json", text)
        source = VERIFIER.read_text(encoding="utf-8")
        for required in ("_deny_reparse_ancestors", "object_pairs_hook=_unique",
                         "parse_float=_number", "parse_constant=_reject_constant"):
            self.assertIn(required, source)

if __name__ == "__main__":
    unittest.main()
