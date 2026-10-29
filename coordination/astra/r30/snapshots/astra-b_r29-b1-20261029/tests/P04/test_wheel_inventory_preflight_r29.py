"""Local tiny wheel bytes exercise the read-only existing P04 probe; no pip/GPU."""
import hashlib
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from packaging.tags import parse_tag

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("p04_wheel_probe", ROOT / "Packages/P04/model_snapshot_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WheelInventoryPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "example_pkg-1.0-py3-none-any.whl"

    def wheel(self, *, name="example-pkg", version="1.0", tag="py3-none-any", python=">=3.10",
              license="Apache-2.0", extra=(), license_header="License-Expression", metadata=None):
        metadata = metadata or f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\nRequires-Python: {python}\n{license_header}: {license}\n"
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
            wheel.writestr("example_pkg-1.0.dist-info/METADATA", metadata)
            wheel.writestr("example_pkg-1.0.dist-info/WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n")
            wheel.writestr("example_pkg/__init__.py", "pass\n")
            for entry, data in extra:
                wheel.writestr(entry, data)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def inspect(self, digest, **changes):
        values = dict(expected_sha256=digest, target_tags=parse_tag("py3-none-any"),
                      target_python="3.12.10", expected_license="Apache-2.0")
        values.update(changes)
        return probe.inspect_wheel(self.path, **values)

    def test_exact_artifact_does_not_claim_rights_or_runtime(self):
        digest = self.wheel()
        result = self.inspect(digest)
        self.assertEqual(result["status"], "ARTIFACT_CONTRACT_MATCH_ONLY")
        self.assertEqual(result["sha256"], digest)
        for key in ("rights_verified", "hardware_verified", "dependency_lock_verified"):
            self.assertIs(result[key], False)

    def test_hash_mismatch_holds_before_zip_parsing(self):
        self.wheel()
        result = self.inspect("0" * 64)
        self.assertEqual(result["reason"], "WHEEL_SHA256_MISMATCH")

    def test_same_inode_changed_after_hash_cannot_publish_old_sha_with_new_metadata(self):
        digest = self.wheel()
        inode = self.path.stat().st_ino
        original_hash = probe._sha256_stream
        def change_after_hash(stream):
            actual = original_hash(stream)
            self.wheel(license="MIT")
            self.assertEqual(self.path.stat().st_ino, inode)
            return actual
        with patch.object(probe, "_sha256_stream", side_effect=change_after_hash):
            result = self.inspect(digest, expected_license="MIT")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "WHEEL_ARTIFACT_CHANGED_DURING_INSPECTION")

    def test_target_tags_and_python_are_caller_supplied_constraints(self):
        digest = self.wheel(python=">=3.12")
        self.assertEqual(self.inspect(digest, target_tags=parse_tag("cp310-cp310-win_amd64"))["reason"], "WHEEL_TARGET_TAG_MISMATCH")
        self.assertEqual(self.inspect(digest, target_python="3.10.0")["reason"], "WHEEL_TARGET_PYTHON_MISMATCH")

    def test_identity_and_tags_must_match_filename(self):
        for override in ({"name": "another"}, {"version": "2.0"}, {"tag": "cp310-cp310-win_amd64"}):
            with self.subTest(override=override):
                result = self.inspect(self.wheel(**override))
                self.assertEqual(result["status"], "HOLD")
                self.assertIn(result["reason"], ("WHEEL_METADATA_IDENTITY_MISMATCH", "WHEEL_TAG_METADATA_MISMATCH"))

    def test_ambiguous_and_oversized_metadata_are_not_parsed(self):
        for extra in (("other-1.0.dist-info/METADATA", "Name: other\n"),
                      ("example_pkg-1.0.dist-info/METADATA", "x" * (1024 * 1024 + 1))):
            with self.subTest(entry=extra[0]):
                result = self.inspect(self.wheel(extra=(extra,)))
                self.assertEqual(result["status"], "HOLD")
        oversized = "Name: example-pkg\nVersion: 1.0\n" + "X: " + "x" * (1024 * 1024)
        self.assertEqual(self.inspect(self.wheel(metadata=oversized))["reason"], "WHEEL_METADATA_SIZE_INVALID")

    def test_duplicate_identity_headers_and_license_mismatch_hold(self):
        self.assertEqual(self.inspect(self.wheel(license="MIT"))["reason"], "WHEEL_DECLARED_LICENSE_MISMATCH")
        metadata = "Name: example-pkg\nName: another\nVersion: 1.0\nLicense-Expression: Apache-2.0\n"
        self.assertEqual(self.inspect(self.wheel(metadata=metadata))["reason"], "WHEEL_METADATA_FIELDS_INVALID")

    def test_legacy_license_field_is_preserved_without_rights_upgrade(self):
        result = self.inspect(self.wheel(license_header="License"))
        self.assertEqual(result["status"], "ARTIFACT_CONTRACT_MATCH_ONLY")
        self.assertEqual(result["license_field"], "License")
        self.assertFalse(result["rights_verified"])

    def test_missing_target_and_hash_are_hold_not_defaults(self):
        digest = self.wheel()
        for changes in ({"target_tags": []}, {"target_python": None}, {"expected_sha256": ""}, {"expected_license": ""}):
            with self.subTest(changes=changes):
                self.assertEqual(self.inspect(digest, **changes)["status"], "HOLD")


if __name__ == "__main__": unittest.main()
