"""Source-only checks: model update keeps STOP while selecting FORSAZH."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import owner_autonomy_mode_stage_v15 as mode


class ModeStageTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "nox"
        self.state = self.root / "state"
        self.state.mkdir(parents=True)
        self.flags = (self.root / "STOP", self.state / "OWNER_MAINTENANCE.flag")
        self.flags[0].write_text("OWNER_MODEL_UPDATE\n")
        self.flags[1].write_text("OWNER_MODEL_UPDATE\n")
        self.patches = (
            patch.object(mode, "ROOT", self.root),
            patch.object(mode, "STATE", self.state),
            patch.object(mode, "MODE_PATH", self.state / "owner_autonomy_mode_v15.json"),
            patch.object(mode, "checked_supervisor", return_value={
                "nox-dispatcher-t855u": "STOPPED",
                "nox-chat-8081": "STOPPED",
                "nox-priority-scheduler": "STOPPED",
                "nox-selfheal": "STOPPED"}),
            patch.object(mode.os, "geteuid", return_value=0),
            patch.dict(os.environ, {"NOX_OWNER_SOURCE_SHA": "a" * 40,
                                    "NOX_OWNER_REQUEST_ID": "3456"})
        )
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_stages_only_mode_without_starting_processes(self):
        self.assertEqual(mode.main(), 0)
        obj = json.loads(mode.MODE_PATH.read_text())
        self.assertEqual(obj["mode_workers"], {"NORMAL": 2, "FORSAZH": 6})
        self.assertEqual(obj["selected"], "FORSAZH")
        self.assertFalse(obj["production_processes_started"])
        self.assertFalse(obj["native_binding_active_verified"])
        self.assertTrue(all(f.is_file() for f in self.flags))
        self.assertEqual(mode.MODE_PATH.stat().st_mode & 0o777, 0o600)

    def test_second_run_cannot_overwrite_owner_mode(self):
        mode.main()
        before = mode.MODE_PATH.read_bytes()
        self.assertEqual(mode.main(), 0)
        self.assertEqual(mode.MODE_PATH.read_bytes(), before)

    def test_missing_stop_holds_and_writes_nothing(self):
        self.flags[1].unlink()
        with self.assertRaisesRegex(mode.Hold, "STOP_NOT_ACTIVE"):
            mode.main()
        self.assertFalse(mode.MODE_PATH.exists())

    def test_symlink_mode_path_is_rejected(self):
        target = self.state / "other"
        target.write_text("foreign")
        mode.MODE_PATH.symlink_to(target)
        with self.assertRaisesRegex(mode.Hold, "PATH_SYMLINK"):
            mode.main()
        self.assertEqual(target.read_text(), "foreign")

    def test_conflicting_old_mode_is_not_overwritten(self):
        mode.MODE_PATH.write_text(json.dumps({"schema": mode.SCHEMA,
            "selected": "NORMAL", "mode_workers": {"NORMAL": 3, "FORSAZH": 6}}))
        before = mode.MODE_PATH.read_bytes()
        with self.assertRaisesRegex(mode.Hold, "EXISTING_OWNER_MODE_CONFLICT"):
            mode.main()
        self.assertEqual(mode.MODE_PATH.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
