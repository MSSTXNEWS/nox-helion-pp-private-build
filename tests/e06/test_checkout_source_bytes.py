"""A Windows-style Git checkout must retain the bytes admitted by source pins."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
P03_UI = "Packages/P03/Source/P03.ModelCenter.Wow/ui.js"


class ExactSourceCheckout(unittest.TestCase):
    def checkout(self, samples):
        # Seed the Git objects directly: the test is about materialization of
        # already reviewed blobs, not normalizing new source during git add.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            files = {".gitattributes": (ROOT / ".gitattributes").read_bytes(), **samples}
            for name, data in files.items():
                digest = subprocess.check_output(
                    ["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                    input=data,
                ).decode().strip()
                subprocess.run(
                    ["git", "-C", str(root), "update-index", "--add",
                     "--cacheinfo", "100644," + digest + "," + name], check=True,
                )
            subprocess.run(
                ["git", "-C", str(root), "-c", "core.autocrlf=true",
                 "checkout-index", "--force", "--all"], check=True,
            )
            return {name: (root / name).read_bytes() for name in samples}

    def test_windows_checkout_preserves_approved_p03_ui_bytes(self):
        original = (ROOT / P03_UI).read_bytes()
        self.assertIn(b"\n", original)
        actual = self.checkout({P03_UI: original})[P03_UI]
        self.assertEqual(len(actual), len(original), "Windows checkout changed source pin length")
        self.assertEqual(actual, original)

    def test_checkout_preserves_existing_crlf_and_binary_blobs(self):
        originals = {
            "fixtures/original-owner.ps1": b"# Original owner bytes\r\nexit 0\r\n",
            "fixtures/original.bin": bytes(range(256)) + b"\r\n\n\x00",
        }
        self.assertEqual(self.checkout(originals), originals)


if __name__ == "__main__":
    unittest.main()
