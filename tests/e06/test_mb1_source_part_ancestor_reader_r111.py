"""R111 MB1 source archive: SHA alone must not admit redirected ancestors."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mb1_r111_source", ROOT / "coordination/e06/mb1_extract_original_sources.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("MB1_R111_ORIGINAL_SOURCE_UNAVAILABLE")
MB1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MB1)


class MB1SourcePartTrustedDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.real = Path(self.temp.name) / "original"
        self.real.mkdir()
        self.data = (b"A" * 20971520, b"B" * 20971520, b"C" * 18421306)
        for index, data in enumerate(self.data):
            (self.real / f"source_{index:02}.part").write_bytes(data)
        self.pin = hashlib.sha256(b"".join(self.data)).hexdigest()

    def read(self, root, digest=None):
        with mock.patch.object(MB1, "ROOT", root), mock.patch.object(
                MB1, "PYSHA", self.pin if digest is None else digest):
            return MB1.join_and_verify_python().getvalue()

    def test_verified_direct_three_parts(self):
        self.assertEqual(self.read(self.real), b"".join(self.data))

    def test_symlinked_ancestor_never_admitted_even_if_sha_matches(self):
        alias = Path(self.temp.name) / "redirected"
        try:
            alias.symlink_to(self.real, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("platform cannot create directory symlink: " + str(exc))
        with self.assertRaisesRegex(Exception, "OUTPUT_PARENT_REPARSE_OR_UNSAFE"):
            self.read(alias)

    def test_leaf_symlink_rejected(self):
        target = self.real / "source_00.part"
        target.rename(self.real / "saved.part")
        try:
            target.symlink_to(self.real / "saved.part")
        except (OSError, NotImplementedError) as exc:
            self.skipTest("platform cannot create file symlink: " + str(exc))
        with self.assertRaisesRegex(Exception, "MB1_SOURCE_PART_MISSING"):
            self.read(self.real)

    def test_wrong_exact_combined_sha_still_hold(self):
        with self.assertRaisesRegex(Exception, "MB1_SOURCE_729_SHA256_HOLD"):
            self.read(self.real, "0" * 64)


if __name__ == "__main__":
    unittest.main()
