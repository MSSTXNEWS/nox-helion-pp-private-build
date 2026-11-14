"""R11 original HOME chatLog TDZ -- strict disposable staging-only repair.

This source regression does not prove installed WebView2 clicks or E07 PASS.
"""
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nox_u07_original_home_tdz", ROOT / "coordination/express/stage_original_five_primary.py"
)
assert SPEC is not None and SPEC.loader is not None
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)
ORIGINAL_DECL = "chatLog=document.getElementById('chat-log'),"
EARLY_ANCHOR = "let chatScrollFrame=0;"
EARLY_DECL = "const chatLog=document.getElementById('chat-log');"


class OriginalHomeChatlogTDZ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        joined = b"".join(
            (ROOT / "donors/P01_C07" / f"P01_C07_{i:02d}.part").read_bytes()
            for i in range(28)
        )
        with zipfile.ZipFile(io.BytesIO(joined)) as donor:
            assert donor.testzip() is None, "U07_ORIGINAL_C07_CRC_HOLD"
            cls.original = donor.read("R11/Assets/index.html")
        assert len(cls.original) == stage.ORIGINAL_BYTES
        assert hashlib.sha256(cls.original).hexdigest() == stage.ORIGINAL_SHA256

    def test_original_tdz_reproduced_and_donor_stays_unchanged(self):
        original = self.original.decode("utf-8-sig")
        self.assertEqual(original.count(ORIGINAL_DECL), 1)
        self.assertEqual(original.count(EARLY_ANCHOR), 1)
        self.assertLess(original.index(EARLY_ANCHOR), original.index(ORIGINAL_DECL))
        self.assertLess(original.index("chatLog.addEventListener("), original.index(ORIGINAL_DECL))
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), stage.ORIGINAL_SHA256)

    def test_derived_published_copy_has_single_early_declaration(self):
        output, receipt = stage.publish(self.original)
        html = output.decode("utf-8")
        self.assertEqual(html.count(EARLY_DECL), 1)
        self.assertNotIn(ORIGINAL_DECL, html)
        self.assertLess(html.index(EARLY_DECL), html.index("chatLog.addEventListener("))
        self.assertLess(html.index(EARLY_DECL), html.index(EARLY_ANCHOR))
        self.assertEqual(output.count(b"data-nox-primary="), 5)
        self.assertNotEqual(output, self.original)
        self.assertEqual(receipt["source_sha256"], stage.ORIGINAL_SHA256)
        self.assertEqual(receipt["published_sha256"], hashlib.sha256(output).hexdigest())
        self.assertEqual(receipt["installed_ui_automation"], "NOT_RUN")
        self.assertIs(receipt["release_accepted"], False)

    def test_immutable_original_source_lock_rejects_any_drift(self):
        drift = bytearray(self.original)
        drift[-16] ^= 1
        with self.assertRaisesRegex(ValueError, "U08_ORIGINAL_HOME_SHA_HOLD"):
            stage.publish(bytes(drift))


if __name__ == "__main__":
    unittest.main()
