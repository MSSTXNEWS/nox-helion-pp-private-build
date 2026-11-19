"""Local fail-closed tests for startup metadata inspection; never contact host."""
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location(
    "boot_hook_attest_test", HERE / "owner_native_boot_hook_attest.py")
FINGERPRINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINGERPRINT)
PRODUCTION_STARTUP_FILES = FINGERPRINT.STARTUP_FILES
TRUSTED_DIRECTORY = FINGERPRINT._trusted_directory


class BootHookAttestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hook = self.root / "onstart.sh"
        self.supervisor = self.root / "supervisord.conf"
        self.observer = self.root / "nox-lifeline-observer.conf"
        self.hook.write_text("#!/bin/sh\n# PRIVATE_START_HOOK_SENTINEL\n")
        self.supervisor.write_text(
            "[include]\nfiles = /etc/supervisor/conf.d/*.conf\n"
            "[unix_http_server]\npassword = PRIVATE_MAIN_CONFIG_SENTINEL\n")
        self.observer.write_text("[program:nox-lifeline-observer]\n"
                                 "command=PRIVATE_OBSERVER_CONFIG_SENTINEL\n")
        self.fixture_files = (
            ("instance_start_hook", str(self.hook), 65_536),
            ("supervisor_main_config", str(self.supervisor), 262_144),
            ("observer_program_config", str(self.observer), 8_192),
        )
        self.paths_patch = patch.object(FINGERPRINT, "STARTUP_FILES",
                                        self.fixture_files)
        self.uid_patch = patch.object(FINGERPRINT, "ROOT_UID", os.getuid())
        # Fixtures live in a disposable test directory. Production parents are
        # still checked as root-owned and not group/world writable.
        self.directory_patch = patch.object(FINGERPRINT, "_trusted_directory",
                                            return_value=True)
        self.paths_patch.start()
        self.uid_patch.start()
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        self.addCleanup(self.uid_patch.stop)
        self.addCleanup(self.paths_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def result(self):
        pin = hashlib.sha256(self.observer.read_bytes()).hexdigest()
        with patch.object(FINGERPRINT, "OBSERVER_PROGRAM_CONFIG_SHA256", pin):
            return FINGERPRINT.attest_boot_hook()

    def test_exact_paths_are_fixed_allowlist_and_metadata_has_no_contents(self):
        self.assertEqual(PRODUCTION_STARTUP_FILES, (
            ("instance_start_hook", "/root/onstart.sh", 65_536),
            ("supervisor_main_config", "/etc/supervisor/supervisord.conf", 262_144),
            ("observer_program_config",
             "/etc/supervisor/conf.d/nox-lifeline-observer.conf", 8_192),
        ))
        # Use fixture paths for execution; production path allowlist above stays fixed.
        report = self.result()
        self.assertEqual(report["schema"], "NOX_BOOT_HOOK_ATTEST_V1")
        self.assertEqual(report["state"], "READ_OK")
        self.assertTrue(report["supervisor_include_loads_observer_config"])
        self.assertTrue(report["observer_program_config_matches_installer_pin"])
        self.assertEqual(len(report["files"]), 3)
        for row in report["files"]:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            for key in ("device", "inode", "mode", "uid", "gid", "nlink",
                        "size_bytes", "mtime_ns", "ctime_ns"):
                self.assertIn(key, row)
        serialized = json.dumps(report, sort_keys=True)
        for secret in ("PRIVATE_START_HOOK_SENTINEL",
                       "PRIVATE_MAIN_CONFIG_SENTINEL",
                       "PRIVATE_OBSERVER_CONFIG_SENTINEL"):
            self.assertNotIn(secret, serialized)
        for row in report["files"]:
            self.assertNotIn("content", row)
        self.assertFalse(report["file_contents_emitted"])
        self.assertFalse(report["secret_values_emitted"])

    def test_wrong_include_pattern_holds_without_returning_config_values(self):
        self.supervisor.write_text(
            "[include]\nfiles = /etc/supervisor/conf.d/private-*.conf\n"
            "password = PRIVATE_WRONG_INCLUDE_SENTINEL\n")
        report = self.result()
        self.assertEqual(report["state"], "HOLD")
        self.assertFalse(report["supervisor_include_loads_observer_config"])
        self.assertIn("OBSERVER_CONFIG_NOT_INCLUDED", report["hold_reasons"])
        self.assertNotIn("PRIVATE_WRONG_INCLUDE_SENTINEL", json.dumps(report))

    def test_observer_pin_mismatch_holds(self):
        with patch.object(FINGERPRINT, "OBSERVER_PROGRAM_CONFIG_SHA256", "0" * 64):
            report = FINGERPRINT.attest_boot_hook()
        self.assertEqual(report["state"], "HOLD")
        self.assertFalse(report["observer_program_config_matches_installer_pin"])
        self.assertIn("OBSERVER_CONFIG_PIN_MISMATCH", report["hold_reasons"])

    def test_missing_file_holds(self):
        self.observer.unlink()
        with patch.object(FINGERPRINT, "OBSERVER_PROGRAM_CONFIG_SHA256", "0" * 64):
            report = FINGERPRINT.attest_boot_hook()
        self.assertEqual(report["state"], "HOLD")
        self.assertEqual(report["files"][-1]["state"], "MISSING")

    def test_safe_read_rejects_symlink_hardlink_nonregular_and_oversize(self):
        outside = self.root / "outside"
        outside.write_text("PRIVATE_SYMLINK_TARGET")
        link = self.root / "link"
        link.symlink_to(outside)
        with self.assertRaises(OSError):
            FINGERPRINT.safe_read(str(link), 100)

        hardlink = self.root / "hardlink"
        os.link(outside, hardlink)
        with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_SHAPE"):
            FINGERPRINT.safe_read(str(hardlink), 100)

        directory = self.root / "directory"
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_SHAPE"):
            FINGERPRINT.safe_read(str(directory), 100)

        oversized = self.root / "oversized"
        oversized.write_bytes(b"x" * 101)
        with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_SHAPE"):
            FINGERPRINT.safe_read(str(oversized), 100)

    def test_safe_read_rejects_non_root_owned_and_writable_files(self):
        with patch.object(FINGERPRINT, "ROOT_UID", 0):
            if os.getuid() != 0:
                with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_SHAPE"):
                    FINGERPRINT.safe_read(str(self.hook), 100)
        self.hook.chmod(stat.S_IMODE(self.hook.stat().st_mode) | 0o020)
        with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_SHAPE"):
            FINGERPRINT.safe_read(str(self.hook), 100)

    def test_parent_directory_trust_check_rejects_writable_directory(self):
        with patch.object(FINGERPRINT, "ROOT_UID", os.getuid()):
            self.assertTrue(TRUSTED_DIRECTORY(self.root.stat()))
            self.root.chmod(0o777)
            self.assertFalse(TRUSTED_DIRECTORY(self.root.stat()))

    def test_read_detects_concurrent_file_change_and_holds(self):
        original_read = FINGERPRINT.os.read
        changed = False

        def read_then_append(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if not changed:
                changed = True
                with self.hook.open("ab") as stream:
                    stream.write(b"changed")
            return data

        with patch.object(FINGERPRINT.os, "read", side_effect=read_then_append):
            with self.assertRaisesRegex(ValueError, "HOLD_STARTUP_FILE_CHANGED"):
                FINGERPRINT.safe_read(str(self.hook), 100)

    def test_exact_operator_route_points_only_to_fixed_inspector(self):
        tree = ast.parse((HERE / "owner_native_operator.py").read_text())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "FILES"
                               for target in node.targets)]
        self.assertEqual(len(assignments), 1)
        files = ast.literal_eval(assignments[0].value)
        self.assertEqual(files["boot_hook_attest"],
                         "nox-control/owner_native_boot_hook_attest.py")

        script = ast.parse((HERE / "owner_native_boot_hook_attest.py").read_text())
        imported = {alias.name for node in ast.walk(script)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        self.assertFalse(imported & {"subprocess", "socket", "requests", "urllib"})

    def test_non_root_owner_context_fails_before_reading_files(self):
        output = io.StringIO()
        env = {"NOX_OWNER_SOURCE_SHA": "a" * 40,
               "NOX_OWNER_REQUEST_ID": "123"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(FINGERPRINT, "ROOT_UID", 0), \
                patch.object(FINGERPRINT.os, "geteuid", return_value=1000), \
                patch.object(FINGERPRINT, "attest_boot_hook",
                             side_effect=AssertionError("must not read")), \
                patch("sys.stdout", output):
            self.assertEqual(FINGERPRINT.main(), 2)
        emitted = output.getvalue()
        self.assertIn('"state":"HOLD"', emitted)
        self.assertIn('"reason":"HOLD_OWNER_CONTEXT"', emitted)
        self.assertNotIn("PRIVATE_", emitted)

    def test_root_owner_output_contains_only_hashes_and_stat(self):
        output = io.StringIO()
        env = {"NOX_OWNER_SOURCE_SHA": "b" * 40,
               "NOX_OWNER_REQUEST_ID": "456"}
        pin = hashlib.sha256(self.observer.read_bytes()).hexdigest()
        with patch.dict(os.environ, env, clear=True), \
                patch.object(FINGERPRINT.os, "geteuid", return_value=os.getuid()), \
                patch.object(FINGERPRINT, "OBSERVER_PROGRAM_CONFIG_SHA256", pin), \
                patch("sys.stdout", output):
            self.assertEqual(FINGERPRINT.main(), 0)
        emitted = output.getvalue()
        self.assertIn("NOX_MAINT_BOOT_HOOK_ATTEST=", emitted)
        self.assertIn("NOX_MAINT_BOOT_HOOK_ATTEST_COMPLETE=true", emitted)
        self.assertIn('"sha256":', emitted)
        for secret in ("PRIVATE_START_HOOK_SENTINEL",
                       "PRIVATE_MAIN_CONFIG_SENTINEL",
                       "PRIVATE_OBSERVER_CONFIG_SENTINEL"):
            self.assertNotIn(secret, emitted)


if __name__ == "__main__":
    unittest.main()
