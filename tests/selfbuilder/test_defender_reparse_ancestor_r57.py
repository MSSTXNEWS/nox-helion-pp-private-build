"""Focused security regressions for original src/nox_selfbuilder/defender_guard.py.

Runs on Linux with a simulated Windows Defender response.  It does not certify
Windows Defender, Authenticode, setup, host IPC, installed UI, or E07.
"""
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[2] / "src" / "nox_selfbuilder" / "defender_guard.py"
spec = importlib.util.spec_from_file_location("nox_defender_guard_r57", SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class TestDefenderReparseAncestor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.outer = self.base / "outer"
        self.root = self.outer / "approved"
        self.root.mkdir(parents=True)
        self.target = self.root / "donor.py"
        self.target.write_bytes(b"reviewed test donor - not executed\n")
        self.runner_calls = 0

    def runner(self, args, **kw):
        self.runner_calls += 1
        self.assertEqual(args[0], "powershell.exe")
        self.assertEqual(kw["env"]["NOX_DONOR_SCAN_FILE"], str(self.target.resolve()))
        return subprocess.CompletedProcess(args, 0, stdout=b'{"state":"DEFENDER_SCAN_REQUESTED_REVIEW_REQUIRED"}')

    def scan(self, run=None, target=None, root=None):
        return guard.scan_donor_file(target or self.target, staging_root=root or self.root,
                                     platform="nt", run=run or self.runner)

    def test_clean_path_requests_review_not_admission(self):
        receipt = self.scan()
        self.assertEqual(receipt["status"], "SCAN_REQUESTED_REVIEW_REQUIRED")
        self.assertTrue(receipt["scan_requested"])
        for field in ("malware_free_proven", "license_approved", "production_admitted", "source_executed"):
            self.assertFalse(receipt[field])
        self.assertEqual(self.runner_calls, 1)

    def test_real_parent_symlink_outside_staging_is_denied(self):
        alias = self.base / "alias"
        alias.symlink_to(self.outer, target_is_directory=True)
        with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_PATH_REPARSE_DENIED"):
            self.scan(target=alias / "approved" / "donor.py", root=alias / "approved")
        self.assertEqual(self.runner_calls, 0)

    def test_windows_junction_attribute_on_grandparent_denied(self):
        original_lstat = Path.lstat
        outer = self.outer

        class WindowsJunctionStat:
            def __init__(self, stat_result):
                self.real = stat_result
                self.st_mode = stat_result.st_mode
                self.st_file_attributes = getattr(stat_result, "st_file_attributes", 0) | 0x400

            def __getattr__(self, attr):
                return getattr(self.real, attr)

        def lstat(path, *a, **kw):
            result = original_lstat(path, *a, **kw)
            return WindowsJunctionStat(result) if path == outer else result

        with mock.patch.object(Path, "lstat", lstat):
            with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_PATH_REPARSE_DENIED"):
                self.scan()
        self.assertEqual(self.runner_calls, 0)

    def test_junction_replaced_during_scan_cannot_produce_positive_receipt(self):
        original_lstat = Path.lstat
        state = {"changed": False}
        outer = self.outer

        class WindowsJunctionStat:
            def __init__(self, info):
                self.info = info
                self.st_mode = info.st_mode
                self.st_file_attributes = 0x400
            def __getattr__(self, attr):
                return getattr(self.info, attr)

        def lstat(path, *a, **kw):
            info = original_lstat(path, *a, **kw)
            return WindowsJunctionStat(info) if path == outer and state["changed"] else info

        def replace_during_scan(*a, **kw):
            result = self.runner(*a, **kw)
            state["changed"] = True
            return result

        with mock.patch.object(Path, "lstat", lstat):
            with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_PATH_REPARSE_DENIED"):
                self.scan(run=replace_during_scan)
        self.assertEqual(self.runner_calls, 1)

    def test_noncanonical_traversal_rejected_without_run(self):
        with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_NONCANONICAL_PATH_DENIED"):
            self.scan(target=self.root / ".." / "approved" / "donor.py")
        self.assertEqual(self.runner_calls, 0)

    def test_non_object_json_receipts_fail_closed(self):
        for obj in ([], None, True, 7, "approved", {"state": []}, {"state": True}):
            with self.subTest(obj=obj):
                output = json.dumps(obj).encode()
                def runner(*a, **kw):
                    return subprocess.CompletedProcess(a, 0, stdout=output)
                receipt = self.scan(run=runner)
                self.assertEqual(receipt["status"], "HOLD")
                self.assertEqual(receipt["reason"], "DEFENDER_UNVERIFIED")
                self.assertFalse(receipt["scan_requested"])

    def test_contradictory_success_receipt_is_hold(self):
        def runner(*a, **kw):
            return subprocess.CompletedProcess(a, 0, stdout=b'{"state":"DEFENDER_SCAN_REQUESTED_REVIEW_REQUIRED","count":99}')
        self.assertEqual(self.scan(run=runner)["status"], "HOLD")

    def test_mutated_donor_is_hold_not_production_admission(self):
        def runner(*a, **kw):
            self.target.write_bytes(b"changed")
            return subprocess.CompletedProcess(a, 0, stdout=b'{"state":"DEFENDER_SCAN_REQUESTED_REVIEW_REQUIRED"}')
        with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_POSTSCAN_SOURCE_CHANGED"):
            self.scan(run=runner)

    def test_outside_staging_is_still_denied(self):
        other = self.base / "other.txt"
        other.write_bytes(b"escape")
        with self.assertRaisesRegex(guard.DefenderHold, "DEFENDER_STAGING_ESCAPE_DENIED"):
            self.scan(target=other)
        self.assertEqual(self.runner_calls, 0)

    def test_non_windows_never_requests_scan(self):
        result = guard.scan_donor_file(self.target, staging_root=self.root, platform="posix", run=self.runner)
        self.assertEqual(result["reason"], "DEFENDER_WINDOWS_ONLY")
        self.assertEqual(self.runner_calls, 0)


if __name__ == "__main__":
    unittest.main()
