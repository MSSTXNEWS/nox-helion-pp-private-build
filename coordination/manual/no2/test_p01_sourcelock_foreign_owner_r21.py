"""Manual #2 source-only QA of P01 exclusive-lock publication on new owner implementation.

Directly imports the real P01 staging code and its existing 28-part ZIP fixture.
Does NOT run CI, NSIS, EXE, or claim native Windows acceptance.
Review exact upstream source preimage on every integration.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import os
import stat
import unittest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/e06/test_stage_p01_shared_zip_guard.py"
SPEC = importlib.util.spec_from_file_location("nox_p01_existing_fixture", FIXTURE)
existing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(existing)


class SourceLockRaceIndependentQA(existing.ReusedCanonicalZipGate):
    def make_complete_wpf_fixture(self):
        names = existing.NEEDED + [
            f"R11/QA/extra-{i:03}.txt"
            for i in range(75 - len(existing.NEEDED))
        ]
        self.create([(name, stat.S_IFREG) for name in names])
        self.work.mkdir(parents=True, exist_ok=True)

    def test_concurrent_foreign_source_lock_must_survive_failed_exclusive_commit(self):
        self.make_complete_wpf_fixture()
        lock = self.work / "source_lock.json"
        foreign = b"FOREIGN_OWNER_SOURCELOCK_DO_NOT_TOUCH"
        self.assertFalse(lock.exists())

        def concurrent_create(_pending, target):
            self.assertEqual(Path(target), lock)
            lock.write_bytes(foreign)
            raise FileExistsError("FOREIGN_SOURCELOCK_CREATED_AFTER_PREFLIGHT")

        with patch.object(existing.STAGE.os, "link", side_effect=concurrent_create):
            with self.assertRaisesRegex(SystemExit, "E06_SOURCELOCK_ALREADY_EXISTS"):
                existing.STAGE.main()

        self.assertEqual(lock.read_bytes(), foreign)
        self.assertFalse((self.work / "R11").exists())
        self.assertFalse(list(self.work.glob(".nox-r11-pending-*")))

    def test_foreign_replacement_during_failed_promotion_must_not_be_unlinked(self):
        self.make_complete_wpf_fixture()
        lock = self.work / "source_lock.json"
        foreign = b"NEW_OWNER_LOCK_AFTER_OLD_HARDLINK"
        original_rename = Path.rename
        reached = []

        def concurrent_replace(source, target):
            if Path(source).name == "R11":
                reached.append(True)
                self.assertTrue(lock.exists())
                lock.unlink()
                lock.write_bytes(foreign)
                raise OSError("PROMOTION_FAILED_AFTER_FOREIGN_REPLACEMENT")
            return original_rename(source, target)

        with patch.object(Path, "rename", new=concurrent_replace):
            with self.assertRaisesRegex(OSError, "PROMOTION_FAILED_AFTER_FOREIGN_REPLACEMENT"):
                existing.STAGE.main()

        self.assertTrue(reached)
        self.assertEqual(lock.read_bytes(), foreign)
        self.assertFalse((self.work / "R11").exists())

    def test_successful_promotion_has_both_original_r11_and_lock(self):
        self.make_complete_wpf_fixture()
        existing.STAGE.main()
        lock = self.work / "source_lock.json"
        self.assertTrue(lock.is_file())
        self.assertFalse(lock.is_symlink())
        self.assertTrue((self.work / "R11/MainWindow.xaml").is_file())
        self.assertTrue((self.work / "R11/App.xaml").is_file())
        self.assertTrue((self.work / "R11/NOX.P01.Shell.csproj").is_file())
        self.assertEqual((self.work / "R11/Assets/index.html").read_bytes(), b"fixture")


if __name__ == "__main__":
    unittest.main()
