"""Original E06 WPF/NSIS builder: strict raw native proof admission regression.

SOURCE-only: Windows WPF, HMAC, SID, STOP, installed E07 are not simulated.
"""
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "coordination/e06/verify_native_receipt_json.py"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"


class NativeProofAdmission(unittest.TestCase):
    def admit(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            receipt = pathlib.Path(directory, "receipt.json")
            receipt.write_bytes(raw)
            return subprocess.run([sys.executable, str(HELPER), str(receipt)],
                                  capture_output=True, text=True, check=False)

    def test_valid_hold_roundtrip_without_grant(self):
        result = self.admit(
            b'{"run_id_matched":true,"release_accepted":false,"phase":"HOLD",'
            b'"routes":{"chat.stop":{"status":"PASS"}}}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertIn('\t{"run_id_matched":true,"release_accepted":false,',
                      result.stdout)

    def test_nested_duplicate_and_last_wins_denied(self):
        for raw in (b'{"status":"HOLD","status":"PASS"}',
                    b'{"routes":{"chat.stop":{"status":"HOLD","status":"PASS"}}}'):
            with self.subTest(raw=raw):
                self.assertNotEqual(self.admit(raw).returncode, 0)

    def test_nonfinite_and_wide_number_denied(self):
        for raw in (b'{"a":NaN}', b'{"a":1e999}',
                    b'{"a":9223372036854775808}'):
            with self.subTest(raw=raw):
                self.assertNotEqual(self.admit(raw).returncode, 0)

    def test_encoding_trailing_and_scalar_denied(self):
        for raw in (b'{"ok":true}\n{}', b'{"ok":"\xff"}',
                    b'[1,2]', b'{}\x00'):
            with self.subTest(raw=raw):
                self.assertNotEqual(self.admit(raw).returncode, 0)

    def test_size_and_reparse_denied(self):
        huge = b'{"a":"' + b'x' * 1048576 + b'"}'
        self.assertNotEqual(self.admit(huge).returncode, 0)
        with tempfile.TemporaryDirectory() as directory:
            original = pathlib.Path(directory, "original.json")
            original.write_bytes(b'{}')
            alias = pathlib.Path(directory, "alias.json")
            try:
                alias.symlink_to(original)
            except OSError:
                self.skipTest("symlink not permitted")
            check = subprocess.run([sys.executable, str(HELPER), str(alias)],
                                   capture_output=True, text=True, check=False)
            self.assertNotEqual(check.returncode, 0)

    def test_original_builder_uses_exact_pinned_helper_before_parse(self):
        raw = HELPER.read_bytes()
        digest = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("$expectedNativeVerifierBlob='" + digest + "'", builder)
        self.assertIn("E06_NATIVE_RECEIPT_STRICT_JSON_HOLD", builder)
        self.assertNotIn(
            "$proof=Get-Content -LiteralPath $proofPath -Raw -Encoding UTF8 | ConvertFrom-Json",
            builder)
        self.assertIn("$nativeProofSha=$strictEntry.Substring(0,64)", builder)
        self.assertIn("E06_NATIVE_STDIO_WINDOWS_RECEIPT_HOLD", builder)


if __name__ == "__main__":
    unittest.main()
