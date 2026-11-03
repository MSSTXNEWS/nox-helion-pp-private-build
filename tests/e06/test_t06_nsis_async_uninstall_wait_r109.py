"""R109: NSIS silent uninstaller child completion vs premature parent exit.

Executable on the original checkout; mocks only registry and delayed filesystem
completion, never replaces native E07 on Windows.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase, main, mock

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "coordination/e06/t06_samevm_installed_smoke.py"
spec = importlib.util.spec_from_file_location("nox_r109_real_smoke", SOURCE)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class EmptyRegistry:
    HKEY_CURRENT_USER = 1
    HKEY_LOCAL_MACHINE = 2
    KEY_WOW64_32KEY = 0x0200
    KEY_WOW64_64KEY = 0x0100
    KEY_READ = 0x20019

    @staticmethod
    def OpenKey(*_args):
        raise FileNotFoundError()

    @staticmethod
    def CloseKey(*_args):
        raise AssertionError("No present registry keys")


class R109AsyncUninstall(TestCase):
    def _fixture(self, root: Path):
        install = root / "app"
        install.mkdir()
        owned = install / "Owned.exe"
        metadata = [install / n for n in (
            "payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe")]
        for p in [owned, *metadata]:
            p.write_bytes(b"original-installed-file")
        return install, owned, metadata

    def test_deferred_child_removal_is_observed_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, owned, metadata = self._fixture(root)
            userdata = root / "user-data.txt"
            userdata.write_text("NO-LOSS", encoding="utf-8")
            def delayed_child():
                time.sleep(0.07)
                for path in [owned, *metadata]:
                    path.unlink()
            child = threading.Thread(target=delayed_child)
            child.start()
            try:
                with mock.patch.dict(sys.modules, {"winreg": EmptyRegistry}):
                    smoke.await_original_uninstall(
                        install, (owned,), timeout_seconds=1, poll_seconds=0.01)
            finally:
                child.join(timeout=2)
            self.assertFalse(child.is_alive())
            self.assertEqual(userdata.read_text(encoding="utf-8"), "NO-LOSS")

    def test_uninstaller_exit_zero_cannot_accept_owned_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, owned, metadata = self._fixture(Path(tmp))
            with mock.patch.dict(sys.modules, {"winreg": EmptyRegistry}):
                with self.assertRaisesRegex(RuntimeError, "MANIFEST_FILE_REMAINS"):
                    smoke.await_original_uninstall(
                        install, (owned,), timeout_seconds=0.04, poll_seconds=0.01)
            self.assertTrue(owned.is_file())
            self.assertTrue(metadata[0].is_file())

    def test_metadata_gone_is_not_enough_when_manifest_file_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, owned, metadata = self._fixture(Path(tmp))
            for p in metadata:
                p.unlink()
            with mock.patch.dict(sys.modules, {"winreg": EmptyRegistry}):
                with self.assertRaisesRegex(RuntimeError, "MANIFEST_FILE_REMAINS"):
                    smoke.await_original_uninstall(
                        install, (owned,), timeout_seconds=0.04, poll_seconds=0.01)

    def test_registry_remains_is_still_hold(self):
        class PresentRegistry(EmptyRegistry):
            @staticmethod
            def OpenKey(*_args):
                return object()
            @staticmethod
            def CloseKey(*_args):
                return None
        with tempfile.TemporaryDirectory() as tmp:
            install, owned, metadata = self._fixture(Path(tmp))
            for p in [owned, *metadata]:
                p.unlink()
            with mock.patch.dict(sys.modules, {"winreg": PresentRegistry}):
                with self.assertRaisesRegex(RuntimeError, "REGISTRY_REMAINS"):
                    smoke.await_original_uninstall(
                        install, (owned,), timeout_seconds=0.04, poll_seconds=0.01)

    def test_reparse_metadata_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install, owned, metadata = self._fixture(root)
            outside = root / "outside"
            outside.write_text("DO NOT TOUCH", encoding="utf-8")
            metadata[0].unlink()
            try:
                metadata[0].symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("Cannot create test symlink")
            with mock.patch.dict(sys.modules, {"winreg": EmptyRegistry}):
                with self.assertRaisesRegex(RuntimeError, "(MANIFEST_FILE_REMAINS|METADATA_REMAINS)"):
                    smoke.await_original_uninstall(
                        install, (owned,), timeout_seconds=0.04, poll_seconds=0.01)
            self.assertEqual(outside.read_text(encoding="utf-8"), "DO NOT TOUCH")


if __name__ == "__main__":
    main()
