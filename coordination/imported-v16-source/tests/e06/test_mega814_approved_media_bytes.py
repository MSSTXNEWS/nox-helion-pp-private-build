"""Approved original MEGA814 media: byte-exact SOURCE admission, never E07.

The six files are the owner's original Google Drive PNGs, not generated
substitutes.  This test neither activates a route nor approves a persona HOLD.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2] / "coordination/mega814"
PNG = b"\x89PNG\r\n\x1a\n"


def require_media(path: Path, expected_sha: str, expected_size: int | None = None):
    if not path.is_file() or path.is_symlink():
        raise AssertionError("MEGA814_OWNER_MEDIA_MISSING_OR_REPARSE")
    data = path.read_bytes()
    if not data.startswith(PNG) or data[12:16] != b"IHDR":
        raise AssertionError("MEGA814_OWNER_MEDIA_NOT_ORIGINAL_PNG")
    if not (100 < len(data) <= 12000000):
        raise AssertionError("MEGA814_OWNER_MEDIA_SIZE_HOLD")
    if expected_size is not None and len(data) != expected_size:
        raise AssertionError("MEGA814_OWNER_MEDIA_SIZE_DRIFT")
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise AssertionError("MEGA814_OWNER_MEDIA_SHA_HOLD")
    return struct.unpack(">II", data[16:24])


class OwnerApprovedMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "manifest.json").read_text("utf-8"))

    def test_menu10_original_pixels_not_reference_substitute(self):
        m = self.manifest["asset"]
        self.assertEqual(m["menu10OwnerOriginal"]["driveFileId"],
                         "1B8rPaZ7dBvn_s8dh-UTUFSj9zLlfrYnk")
        self.assertEqual(m["menu10SHA256"],
                         "1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca")
        self.assertEqual(m["menu10OwnerOriginal"]["sha256"], m["menu10SHA256"])
        self.assertEqual(require_media(ROOT / m["menu10OwnerOriginal"]["file"],
                         m["menu10SHA256"], m["menu10OwnerOriginal"]["bytes"]), (1672, 941))
        reference = ROOT / "reference/NOX_HELION_MENU_LAVA_WORLD_CURRENT_20261022.png"
        self.assertNotEqual(m["menuReferenceSHA256"], m["menu10SHA256"])
        self.assertEqual(require_media(reference, m["menuReferenceSHA256"]), (1672, 941))

    def test_original_persona_pixels_preserve_identity_holds(self):
        personas = self.manifest["personas"]
        self.assertEqual({p["id"] for p in personas}, {"KV", "AM", "LA", "EV", "KW"})
        expected = {"KV", "AM", "LA", "KW"}
        allowed = {p["id"] for p in personas if p["status"] != "IDENTITY_CONFLICT_HOLD"}
        self.assertEqual(allowed, expected)
        for p in personas:
            target = ROOT / "approved_persona" / p["file"]
            if p["status"] == "IDENTITY_CONFLICT_HOLD":
                self.assertFalse(target.exists(), "do not package disputed EV identity")
                continue
            with self.subTest(persona=p["id"]):
                require_media(target, p["sha256"])

    def test_tampered_media_rejected_without_touching_original(self):
        src = ROOT / self.manifest["asset"]["menu10OwnerOriginal"]["file"]
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "menu10.png"
            shutil.copyfile(src, dst)
            raw = bytearray(dst.read_bytes())
            raw[-1] ^= 1
            dst.write_bytes(raw)
            with self.assertRaisesRegex(AssertionError, "MEDIA_SHA_HOLD"):
                require_media(dst, self.manifest["asset"]["menu10SHA256"], 2955611)


if __name__ == "__main__":
    unittest.main()
