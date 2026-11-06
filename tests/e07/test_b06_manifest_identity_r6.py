"""B06 SOURCE_ONLY: installed NSIS marker and manifest must bind to one identity.

Temporary files only; never labels a Windows installer/E07 as accepted.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "nox_e07_b06_installed_identity",
    Path(__file__).resolve().parents[2] / "coordination/e07/independent_setup_e07.py")
E07 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E07)


class InstalledManifestIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marker = self.root / "nox-p01-owned.txt"
        self.marker.write_text("NOXHELION.P01 V16\n", encoding="utf-8")
        self.exe = self.root / "NOX.P01.Shell.exe"
        self.exe.write_bytes(b"MZ" + b"\0" * 128)
        self.manifest = self.root / "payload.sha256.json"
        self.record = {
            "schema": "NOX_P01_PAYLOAD_SHA256_V1",
            "entrypoint": "NOX.P01.Shell.exe",
            "files": [{
                "path": self.exe.name,
                "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                "bytes": self.exe.stat().st_size,
            }],
        }
        self.manifest.write_text(json.dumps(self.record), encoding="utf-8")

    def test_valid_original_owned_payload(self):
        document, files = E07.manifest_owner(self.root)
        self.assertEqual(document["schema"], "NOX_P01_PAYLOAD_SHA256_V1")
        self.assertEqual(files, (self.exe,))

    def test_foreign_marker_refused(self):
        self.marker.write_text("FOREIGN", encoding="utf-8")
        with self.assertRaisesRegex(E07.Hold, "E07_INSTALLED_OWNER_MARKER_HOLD"):
            E07.manifest_owner(self.root)

    def test_hardlinked_marker_refused_without_delete(self):
        foreign = self.root / "foreign-marker"
        try:
            os.link(self.marker, foreign)
        except OSError:
            self.skipTest("Host does not support hardlinks")
        with self.assertRaises(E07.Hold):
            E07.manifest_owner(self.root)
        self.assertTrue(foreign.exists())

    def test_marker_identical_content_swap_before_open_refused(self):
        real_open = E07.os.open
        switched = []
        def substitute(path, flags, *args, **kwargs):
            if Path(path) == self.marker and not switched:
                replacement = self.root / "replacement"
                replacement.write_bytes(self.marker.read_bytes())
                os.replace(replacement, self.marker)
                switched.append(True)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(E07.os, "open", side_effect=substitute):
            with self.assertRaisesRegex(E07.Hold, "MARKER_IDENTITY_HOLD"):
                E07.manifest_owner(self.root)
        self.assertEqual(switched, [True])

    def test_manifest_identical_content_swap_before_open_refused(self):
        real_open = E07.os.open
        switched = []
        def substitute(path, flags, *args, **kwargs):
            if Path(path) == self.manifest and not switched:
                replacement = self.root / "replacement"
                replacement.write_bytes(self.manifest.read_bytes())
                os.replace(replacement, self.manifest)
                switched.append(True)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(E07.os, "open", side_effect=substitute):
            with self.assertRaisesRegex(E07.Hold, "E07_INSTALLED_MANIFEST_INVALID_JSON_HOLD"):
                E07.manifest_owner(self.root)
        self.assertEqual(switched, [True])

    def test_duplicate_nested_manifest_field_remains_hold(self):
        raw = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(raw.replace('"bytes": 130', '"bytes": 130, "bytes": 130'),
                                 encoding="utf-8")
        with self.assertRaisesRegex(E07.Hold, "E07_INSTALLED_MANIFEST_DUPLICATE_FIELD_HOLD"):
            E07.manifest_owner(self.root)

    def test_nonfinite_manifest_field_remains_hold(self):
        self.record["files"][0]["bytes"] = float("nan")
        self.manifest.write_text(json.dumps(self.record), encoding="utf-8")
        with self.assertRaisesRegex(E07.Hold, "E07_INSTALLED_MANIFEST_NONFINITE_HOLD"):
            E07.manifest_owner(self.root)


if __name__ == "__main__":
    unittest.main()
