"""U09 focused physical-file regression: frozen Setup SHA and PE share one fd.

Source-only test on temporary regular files; not an E07 installer acceptance.
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "coordination/e07/independent_setup_e07.py"
SPEC = importlib.util.spec_from_file_location("nox_e07_u09", FILE)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class FrozenSetupDescriptor(unittest.TestCase):
    def test_single_fd_sha_and_header_match_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw = b"MZ" + bytes(62) + b"PE\0\0" + bytes(6000)
            path = root / "Setup.exe"
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            got, header = MOD.installed_file_sha_locked(
                path, root, len(raw), digest, return_pe_header=True)
            self.assertEqual(got, digest)
            self.assertEqual(header, raw[:4096])
            self.assertEqual(header[64:68], b"PE\0\0")
            self.assertEqual(MOD.installed_file_sha_locked(
                path, root, len(raw), digest), digest)

    def test_same_byte_replacement_before_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "Setup.exe"
            raw = b"MZ" + b"X" * 6000
            path.write_bytes(raw)
            real_open = MOD.os.open
            swaps = []
            def intercept(candidate, flags, *args, **kwargs):
                if Path(candidate) == path and not swaps:
                    alternate = root / "replacement.exe"
                    alternate.write_bytes(raw)
                    os.replace(alternate, path)
                    swaps.append(1)
                return real_open(candidate, flags, *args, **kwargs)
            with patch.object(MOD.os, "open", side_effect=intercept):
                with self.assertRaisesRegex(
                        MOD.Hold, "E07_INSTALLED_FILE_OPEN_IDENTITY_HOLD"):
                    MOD.installed_file_sha_locked(
                        path, root, len(raw), hashlib.sha256(raw).hexdigest(),
                        return_pe_header=True)
            self.assertEqual(swaps, [1])
            self.assertEqual(path.read_bytes(), raw)

    def test_wrong_setup_hash_never_returns_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "Setup.exe"
            path.write_bytes(b"MZ" + b"Z" * 6000)
            with self.assertRaisesRegex(MOD.Hold, "E07_INSTALLED_FILE_SHA_HOLD"):
                MOD.installed_file_sha_locked(
                    path, root, path.stat().st_size, "0" * 64,
                    return_pe_header=True)

    def test_setup_lock_uses_locked_header_not_second_path_open(self):
        source = FILE.read_text(encoding="utf-8")
        segment = source.split("def setup_lock(", 1)[1].split(
            "\ndef manifest_owner(", 1)[0]
        self.assertIn("return_pe_header=True", segment)
        self.assertNotIn("sha256(setup)", segment)
        self.assertNotIn('with setup.open("rb")', segment)
        self.assertIn("E07_SETUP_PARENT_REPARSE_HOLD", segment)
        self.assertIn('"independent_e07":"HOLD"', source)


if __name__ == "__main__":
    unittest.main()
