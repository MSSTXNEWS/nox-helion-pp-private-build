"""NO-LOSS real disposable D02 staging: same-inode foreign-write race."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "coordination/express/publish_original_d02_primary_u12.py"
spec = importlib.util.spec_from_file_location("u05_d02_publisher", SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
PRIMARY = ("CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS")


def fixture(root):
    source = root / "R11"
    home = source / "Assets" / "index.html"
    home.parent.mkdir(parents=True)
    original = b"immutable-disposable-original"
    home.write_bytes(original)
    published = original + b"\n" + b"\n".join(
        b'data-nox-primary="' + name.encode() + b'"' for name in PRIMARY)
    proof = dict(source_sha256=hashlib.sha256(original).hexdigest(),
                 published_sha256=hashlib.sha256(published).hexdigest(),
                 published_bytes=len(published), visible_primary_buttons=list(PRIMARY),
                 installed_ui_automation="NOT_RUN", release_accepted=False)
    return source, home, root / "receipt.json", home.with_name("index.html.nox-u12-pending"), original, published, proof


class NoLossCleanup(unittest.TestCase):
    def test_owned_publish_succeeds_without_release_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            src, home, receipt, staging, original, published, proof = fixture(Path(temp))
            with mock.patch.object(publisher, "publish", return_value=(published, proof)):
                result = publisher.stage(src, receipt)
            self.assertEqual(home.read_bytes(), published)
            self.assertTrue(receipt.is_file())
            self.assertFalse(staging.exists())
            self.assertEqual(result["independent_e07"], "HOLD")

    def test_unchanged_owned_artifacts_cleaned_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            src, home, receipt, staging, original, published, proof = fixture(Path(temp))
            with mock.patch.object(publisher, "publish", return_value=(published, proof)):
                with mock.patch.object(publisher.os, "replace", side_effect=OSError("PUBLISH_HOLD")):
                    with self.assertRaisesRegex(OSError, "PUBLISH_HOLD"):
                        publisher.stage(src, receipt)
            self.assertEqual(home.read_bytes(), original)
            self.assertFalse(staging.exists())
            self.assertFalse(receipt.exists())

    def test_foreign_same_inode_staging_write_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            src, home, receipt, staging, original, published, proof = fixture(Path(temp))
            foreign = b"FOREIGN_STAGE_BYTES"
            def race(source, destination):
                staging.write_bytes(foreign)
                raise OSError("STAGING_RACE")
            with mock.patch.object(publisher, "publish", return_value=(published, proof)):
                with mock.patch.object(publisher.os, "replace", side_effect=race):
                    with self.assertRaisesRegex(OSError, "STAGING_RACE"):
                        publisher.stage(src, receipt)
            self.assertEqual(home.read_bytes(), original)
            self.assertEqual(staging.read_bytes(), foreign)
            self.assertFalse(receipt.exists())

    def test_foreign_same_inode_receipt_write_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            src, home, receipt, staging, original, published, proof = fixture(Path(temp))
            foreign = b"FOREIGN_RECEIPT_BYTES"
            def race(source, destination):
                receipt.write_bytes(foreign)
                raise OSError("RECEIPT_RACE")
            with mock.patch.object(publisher, "publish", return_value=(published, proof)):
                with mock.patch.object(publisher.os, "replace", side_effect=race):
                    with self.assertRaisesRegex(OSError, "RECEIPT_RACE"):
                        publisher.stage(src, receipt)
            self.assertEqual(home.read_bytes(), original)
            self.assertFalse(staging.exists())
            self.assertEqual(receipt.read_bytes(), foreign)


if __name__ == "__main__":
    unittest.main()
