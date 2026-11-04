"""G1 source-only regression: Python Windows junctions are not POSIX symlinks.
This does not accept any Windows installer, registry or independent E07 gate.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nox_p03_verify_junction_u12", ROOT / "coordination/express/verify_p03.py")
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class VerifyP03JunctionFailClosed(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "Packages/P03/Source"
        self.source_dir.mkdir(parents=True)
        self.payload = self.source_dir / "owned.bin"
        data = b"SOURCE_PINNED_SAMPLE"
        self.payload.write_bytes(data)
        blob = hashlib.sha1(
            ("blob " + str(len(data))).encode("ascii") + b"\0" + data
        ).hexdigest()
        (self.root / "P03_PINNED_GIT_BLOBS.json").write_text(json.dumps({
            "schema": "NOX_EXPRESS_E03_OWNER_PINNED_V1",
            "run_id": "U12_REGRESSION_NOT_RELEASE",
            "source_files": 1,
            "pins": [{"path": "Packages/P03/Source/owned.bin",
                      "git_blob_sha1": blob, "bytes": len(data)}],
        }), encoding="utf-8")
        self.registry_path = self.root / "verify_p03.py"

    def run_verifier(self):
        with patch.object(verifier, "F", self.registry_path):
            return verifier.verify(self.root)

    def test_regular_source_is_still_accepted_by_sha(self):
        result = self.run_verifier()
        self.assertEqual(result["verified_count"], 1)
        self.assertEqual(result["status"], "SOURCE_VERIFIED_NOT_RELEASE")

    def test_windows_file_junction_rejected_despite_matching_sha(self):
        with patch.object(Path, "is_junction",
                          lambda path: path == self.payload):
            with self.assertRaisesRegex(ValueError, "MISSING_OR_SYMLINK"):
                self.run_verifier()
        self.assertEqual(self.payload.read_bytes(), b"SOURCE_PINNED_SAMPLE")

    def test_windows_directory_junction_rejected_despite_matching_sha(self):
        with patch.object(Path, "is_junction",
                          lambda path: path == self.source_dir):
            with self.assertRaisesRegex(ValueError, "MISSING_OR_SYMLINK"):
                self.run_verifier()
        self.assertEqual(self.payload.read_bytes(), b"SOURCE_PINNED_SAMPLE")


    def test_source_root_symlink_rejected_before_resolve(self):
        alias = self.root / "root_alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as ex:
            self.skipTest("Symlink privilege unavailable on this Windows runner: " + str(ex))
        with patch.object(verifier, "F", self.registry_path), \
             patch.object(sys, "argv", ["verify_p03.py", "--root", str(alias)]):
            self.assertEqual(verifier.main(), 2)
        self.assertEqual(self.payload.read_bytes(), b"SOURCE_PINNED_SAMPLE")

    def test_source_root_windows_junction_rejected_before_resolve(self):
        # A platform's resolve() can erase the junction marker. Simulate it
        # on a real directory and require a pre-resolution fail-closed gate.
        with patch.object(verifier, "F", self.registry_path), \
             patch.object(Path, "is_junction", lambda path: path == self.root), \
             patch.object(sys, "argv", ["verify_p03.py", "--root", str(self.root)]):
            self.assertEqual(verifier.main(), 2)
        self.assertEqual(self.payload.read_bytes(), b"SOURCE_PINNED_SAMPLE")


if __name__ == "__main__":
    main()
