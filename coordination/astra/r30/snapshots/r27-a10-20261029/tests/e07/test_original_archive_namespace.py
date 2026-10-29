"""E07-SOURCE-03: adversarial tests of the *existing* ZIP source validator.

No replacement validator, no original build ZIP edits, no release acceptance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import pathlib
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "coordination/source-lock/verify_original_archive.py"
spec = importlib.util.spec_from_file_location("nox_original_archive_validator", PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def zip_entry(name, kind=None):
    entry = zipfile.ZipInfo(name)
    entry.create_system = 3
    if kind is not None:
        entry.external_attr = (kind | 0o600) << 16
    return entry


def archive_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, kind in entries:
            archive.writestr(zip_entry(name, kind), b"" if name.endswith("/") else b"safe")
    return stream.getvalue()


class ExistingValidatorNamespaceTests(unittest.TestCase):
    def check_rejected(self, names, code):
        blob = archive_bytes(names)
        with tempfile.TemporaryDirectory(prefix="e07-source03-") as temp:
            root = pathlib.Path(temp)
            cuts = (len(blob) // 3, len(blob) * 2 // 3)
            fragments = (blob[:cuts[0]], blob[cuts[0]:cuts[1]], blob[cuts[1]:])
            for part, chunk in zip(validator.PARTS, fragments):
                (root / part).write_bytes(chunk)
            pins = tuple(hashlib.sha1(b"blob " + str(len(p)).encode() + b"\0" + p).hexdigest() for p in fragments)
            with patch.object(validator, "EXPECTED_SIZE", len(blob)), \
                 patch.object(validator, "EXPECTED_PART_SIZES", tuple(map(len, fragments))), \
                 patch.object(validator, "EXPECTED_PART_GIT_BLOBS", pins), \
                 patch.object(validator, "EXPECTED_SHA256",
                                   hashlib.sha256(blob).hexdigest()):
                with self.assertRaisesRegex(ValueError, code):
                    validator.audit(root, sum(not name.endswith("/") for name, _ in names))

    def test_file_ancestor_then_child(self):
        self.check_rejected([("assets", None), ("assets/home.png", None)],
                            "File used as parent")

    def test_child_then_file_ancestor(self):
        self.check_rejected([("assets/home.png", None), ("assets", None)],
                            "File conflicts with directory")

    def test_implicit_directory_casefold_collision(self):
        self.check_rejected([("Models/weights.gguf", None), ("models", None)],
                            "File conflicts with directory")

    def test_explicit_dir_and_same_name_file(self):
        self.check_rejected([("assets/", stat.S_IFDIR), ("assets", stat.S_IFREG)],
                            "Duplicate/case collision")

    def test_special_unix_nodes(self):
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK,
                     stat.S_IFCHR, stat.S_IFBLK):
            with self.subTest(kind=kind):
                self.check_rejected([("special-node", kind)], "Symlink/special file")

    def test_unix_type_mismatch(self):
        self.check_rejected([("looks-like-file", stat.S_IFDIR)], "kind/type mismatch")
        self.check_rejected([("looks-like-dir/", stat.S_IFREG)], "kind/type mismatch")

    def test_valid_hierarchical_zip_still_passes(self):
        blob = archive_bytes([
            ("R11/", stat.S_IFDIR),
            ("R11/Assets/", stat.S_IFDIR),
            ("R11/Assets/index.html", stat.S_IFREG),
            ("R11/Assets/core01.png", stat.S_IFREG),
        ])
        with tempfile.TemporaryDirectory(prefix="e07-source03-ok-") as temp:
            root = pathlib.Path(temp)
            cuts = (len(blob) // 3, len(blob) * 2 // 3)
            fragments = (blob[:cuts[0]], blob[cuts[0]:cuts[1]], blob[cuts[1]:])
            for part, chunk in zip(validator.PARTS, fragments):
                (root / part).write_bytes(chunk)
            pins = tuple(hashlib.sha1(b"blob " + str(len(p)).encode() + b"\0" + p).hexdigest() for p in fragments)
            with patch.object(validator, "EXPECTED_SIZE", len(blob)), \
                 patch.object(validator, "EXPECTED_PART_SIZES", tuple(map(len, fragments))), \
                 patch.object(validator, "EXPECTED_PART_GIT_BLOBS", pins), \
                 patch.object(validator, "EXPECTED_SHA256",
                                   hashlib.sha256(blob).hexdigest()):
                receipt = validator.audit(root, 2)
            self.assertEqual(receipt["file_count"], 2)
            self.assertEqual(receipt["zip_sha256"], hashlib.sha256(blob).hexdigest())
            self.assertEqual(len(receipt["files"]), 2)


    def test_equal_combined_zip_sha_cannot_hide_shifted_part_boundary(self):
        blob = archive_bytes([("good/file.txt", stat.S_IFREG)])
        cuts = (len(blob) // 3, len(blob) * 2 // 3)
        original = (blob[:cuts[0]], blob[cuts[0]:cuts[1]], blob[cuts[1]:])
        shifted = (blob[:cuts[0] + 1], blob[cuts[0] + 1:cuts[1]], blob[cuts[1]:])
        self.assertEqual(b"".join(shifted), blob)
        self.assertEqual(hashlib.sha256(b"".join(shifted)).hexdigest(),
                         hashlib.sha256(blob).hexdigest())
        with tempfile.TemporaryDirectory(prefix="e07-boundary-") as temp:
            root = pathlib.Path(temp)
            for name, contents in zip(validator.PARTS, shifted):
                (root / name).write_bytes(contents)
            pins = tuple(hashlib.sha1(b"blob " + str(len(p)).encode() + b"\0" + p).hexdigest() for p in original)
            with patch.object(validator, "EXPECTED_SIZE", len(blob)), \
                 patch.object(validator, "EXPECTED_PART_SIZES", tuple(map(len, original))), \
                 patch.object(validator, "EXPECTED_PART_GIT_BLOBS", pins), \
                 patch.object(validator, "EXPECTED_SHA256", hashlib.sha256(blob).hexdigest()):
                with self.assertRaisesRegex(ValueError, "Part sizes mismatch"):
                    validator.audit(root, 1)


if __name__ == "__main__":
    unittest.main()
