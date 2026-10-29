"""Source-derived negative regression for P01 post-publish SourceLock failure.

Uses the existing tested 28-part donor ZIP fixture and imports the real stage_p01.py.
Must be RED on Git blob b0bd954407949965e4871acaa9f15ccc060e3187.
Owner T06 should repair the exact file and obtain GREEN on its own checkout.
No EXE/CI/installer is built.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE_TEST = ROOT / "tests/e06/test_stage_p01_shared_zip_guard.py"
spec = importlib.util.spec_from_file_location("_nox_p01_fixture", SOURCE_TEST)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class SourceLockCollisionAfterExtract(fixture.ReusedCanonicalZipGate):
    def test_late_exclusive_lock_failure_must_leave_no_orphan_r11(self):
        # The real fixture constructs exactly 28 pinned ZIP pieces with the
        # mandatory original WPF XAML, project, bridge and installer paths.
        names = fixture.NEEDED + [
            f"R11/QA/extra-{i:03}.txt"
            for i in range(75 - len(fixture.NEEDED))
        ]
        self.create([(name, 0o100000) for name in names])
        lock_path = self.work / "source_lock.json"
        original_open = Path.open
        attempted = []

        def fail_exclusive_lock(path, mode="r", *args, **kwargs):
            if str(path) == str(lock_path) and mode == "x":
                attempted.append(True)
                # Simulate concurrent lock owner appearing after initial
                # existence preflight: the write never acquired ownership.
                raise FileExistsError("P01_SOURCELOCK_EXCLUSIVE_CONFLICT")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_exclusive_lock):
            with self.assertRaisesRegex(FileExistsError, "P01_SOURCELOCK_EXCLUSIVE_CONFLICT"):
                fixture.STAGE.main()

        self.assertTrue(attempted, "The test must reach the actual lock commit")
        self.assertFalse(lock_path.exists(), "Do not invent or overwrite lock")
        self.assertFalse((self.work / "R11").exists(),
                         "R11 must not be visible after lock commit failed")

    def test_owner_tree_survives_initial_lock_conflict(self):
        names = fixture.NEEDED + [
            f"R11/QA/extra-{i:03}.txt"
            for i in range(75 - len(fixture.NEEDED))
        ]
        self.create([(name, 0o100000) for name in names])
        self.work.mkdir(parents=True, exist_ok=True)
        lock_path = self.work / "source_lock.json"
        original_bytes = b"EXISTING_OWNER_LOCK_MUST_SURVIVE"
        lock_path.write_bytes(original_bytes)
        with self.assertRaisesRegex(SystemExit, "E06_SOURCELOCK_ALREADY_EXISTS"):
            fixture.STAGE.main()
        self.assertEqual(lock_path.read_bytes(), original_bytes)
        self.assertFalse((self.work / "R11").exists())


if __name__ == "__main__":
    unittest.main()
