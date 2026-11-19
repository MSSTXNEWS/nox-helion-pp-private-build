"""Bounded malformed-input acceptance; synthetic bytes, no native mutations."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from nox_runpod.teacher_mesh.v61 import restore_offsite_chunks as module

INDEX = "NOX_V61_CHUNK_INDEX.json"

class TestIndexBounds(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "result.age"
        self.parts = [b"one", b"two", b"three", b"four"]
        self.payload = b"".join(self.parts)
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.index = {"schema": "NOX_V61_ENCRYPTED_CHUNKS_V1", "part_count": 4,
            "ciphertext_total_bytes": len(self.payload), "ciphertext_sha256": self.sha,
            "parts": [{"part": i, "file": f"NOX_V61_CIPHER.part{i:02d}",
                "size_bytes": len(part), "sha256": hashlib.sha256(part).hexdigest()}
                for i, part in enumerate(self.parts, 1)]}

    def write_parts(self, raw=None):
        raw = json.dumps(self.index).encode() if raw is None else raw
        for i, part in enumerate(self.parts, 1):
            with zipfile.ZipFile(self.root / f"NOX_V61_CIPHERTEXT_PART_{i:02d}_20261114.zip",
                                 "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"NOX_V61_CIPHER.part{i:02d}", part)
                z.writestr(INDEX, raw)

    def run_restore(self):
        return module.restore(self.root, self.out, expected_sha=self.sha,
                              expected_bytes=len(self.payload))

    def hold(self, raw=None):
        self.write_parts(raw)
        with self.assertRaisesRegex(ValueError, "^HOLD_"):
            self.run_restore()
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob(".nox-v61-*.partial")), [])

    def test_valid_compressed_roundtrip(self):
        self.write_parts()
        self.assertEqual(self.run_restore()["state"], "REASSEMBLED_SHA_VERIFIED")
        self.assertEqual(self.out.read_bytes(), self.payload)

    def test_non_object_index_is_controlled_hold(self):
        for value in ([], None, 7, "text", True):
            with self.subTest(value=value):
                self.hold(json.dumps(value).encode())

    def test_oversized_index_rejected_before_decompression(self):
        raw = json.dumps(self.index).encode() + b" " * 65536
        self.write_parts(raw)
        real_open = zipfile.ZipFile.open
        def guarded_open(archive, name, *args, **kwargs):
            resolved = name.filename if isinstance(name, zipfile.ZipInfo) else name
            if resolved == INDEX:
                self.fail("Oversized index must be rejected before decompression")
            return real_open(archive, name, *args, **kwargs)
        with patch.object(zipfile.ZipFile, "open", guarded_open):
            with self.assertRaisesRegex(ValueError, "^HOLD_"):
                self.run_restore()
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob(".nox-v61-*.partial")), [])

    def test_duplicate_json_keys_rejected(self):
        raw = json.dumps(self.index).replace('"part_count": 4', '"part_count": 9, "part_count": 4')
        self.hold(raw.encode())

    def test_nonfinite_json_rejected(self):
        raw = json.dumps(self.index)[:-1] + ', "ignored": NaN}'
        self.hold(raw.encode())

    def test_deep_json_is_controlled_hold(self):
        self.hold(("[" * 1500 + "0" + "]" * 1500).encode())

    def test_invalid_utf8_is_controlled_hold(self):
        self.hold(b"\xff")

    def test_float_part_count_rejected(self):
        self.index["part_count"] = 4.0
        self.hold()

    def test_float_total_rejected(self):
        self.index["ciphertext_total_bytes"] = float(len(self.payload))
        self.hold()

    def test_extra_parts_rejected(self):
        self.index["parts"].append(copy.deepcopy(self.index["parts"][-1]))
        self.hold()

    def test_nonlist_parts_rejected(self):
        self.index["parts"] = {}
        self.hold()

    def test_nondict_part_rejected(self):
        self.index["parts"][0] = []
        self.hold()

    def test_boolean_part_number_rejected(self):
        self.index["parts"][0]["part"] = True
        self.hold()

    def test_float_part_size_rejected(self):
        self.index["parts"][0]["size_bytes"] = 3.0
        self.hold()

    def test_wrong_part_size_sum_rejected(self):
        self.index["parts"][0]["size_bytes"] += 1
        self.hold()

    def test_invalid_pinned_hash_controlled_hold(self):
        self.write_parts()
        for digest in (None, 99, "z" * 64, "A" * 64):
            with self.subTest(digest=digest):
                with self.assertRaisesRegex(ValueError, "^HOLD_PINNED_MANIFEST"):
                    module.restore(self.root, self.out, expected_sha=digest,
                                   expected_bytes=len(self.payload))
        self.assertFalse(self.out.exists())

    def test_input_archives_unchanged(self):
        self.write_parts()
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.zip')}
        self.run_restore()
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.zip')}
        self.assertEqual(before, after)

if __name__ == "__main__":
    unittest.main()
