"""Offline tests with a fake restic transport: never touch real user data."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MOD = Path(__file__).with_name("p01_restic_backup_port.py")
spec = importlib.util.spec_from_file_location("p01_restic_backup_port", MOD)
import sys
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

class BackupAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.exe = root / "restic.exe"
        self.exe.write_bytes(b"mock restic executable")
        self.repo = root / "repository"
        self.repo.mkdir()
        self.secret = root / "password-file"
        self.secret.write_bytes(b"native owned secret")
        self.source = root / "user_data"
        self.source.mkdir()
        self.target = root / "empty_restore_target"
        self.target.mkdir()
        self.hash = sha256(self.exe.read_bytes()).hexdigest()
        self.approved = True
        self.stopped = False
        self.calls = []
        self.profile = mod.TrustedResticProfile(self.exe, self.hash, self.repo, self.secret,
                                                (self.source,), self.target)
    def run_restic(self, argv, *, stop):
        self.calls.append(argv)
        return 0, json.dumps({"message_type": "summary", "snapshot_id": "abcdef12345678"}) + "\n"
    def port(self, *, profile=None, snapshot="abcdef12345678"):
        return mod.P01ResticBackupPort(profile or self.profile,
                 native_permission=lambda _s, _op: self.approved,
                 native_snapshot=lambda _s: snapshot,
                 native_stop=lambda: self.stopped,
                 runner=self.run_restic)
    def test_backup_reuses_verified_restic_no_shell_and_returns_real_summary(self):
        result = self.port()(object(), {"operation": "backup"})
        self.assertEqual(result["snapshot_id"], "abcdef12345678")
        self.assertFalse(result["accepted"])
        self.assertEqual(self.calls[0][-4:], ["backup", "--json", "--", str(self.source)])
    def test_no_native_consent_no_native_call(self):
        self.approved = False
        with self.assertRaises(mod.BackupDenied):
            self.port()(object(), {"operation": "backup"})
        self.assertEqual(self.calls, [])
    def test_command_injection_not_supported(self):
        for data in ({"operation":"backup","shell":"powershell"},
                     {"operation":"delete"}, {"operation":"restore","target":"C:\\Users"}):
            with self.assertRaises(mod.BackupDenied):
                self.port()(object(), data)
        self.assertEqual(self.calls, [])
    def test_pin_drift_fails_closed(self):
        self.exe.write_bytes(b"a different binary")
        self.assertFalse(self.port().available())
        with self.assertRaises(mod.BackupHold):
            self.port()(object(), {"operation": "backup"})
    def test_stop_fails_closed(self):
        self.stopped = True
        with self.assertRaises(mod.BackupHold):
            self.port()(object(), {"operation": "backup"})
        self.assertEqual(self.calls, [])
    def test_restore_must_target_empty_native_folder(self):
        (self.target / "existing.file").write_text("preserve me")
        with self.assertRaises(mod.BackupHold):
            self.port()(object(), {"operation": "restore"})
        self.assertEqual(self.calls, [])
    def test_restore_never_claims_user_files_verified_from_exit_zero(self):
        result = self.port()(object(), {"operation": "restore"})
        self.assertEqual(result["status"], "RESTORE_EXIT_ZERO_NEEDS_NATIVE_FILE_VERIFICATION")
        self.assertFalse(result["accepted"])
        self.assertEqual(self.calls[0][-4:], ["restore", "abcdef12345678", "--target", str(self.target)])
    def test_snapshot_must_be_selected_by_native_owner(self):
        with self.assertRaises(mod.BackupDenied):
            self.port(snapshot="../snapshot")(object(), {"operation": "restore"})
        self.assertEqual(self.calls, [])
    def test_native_symlinks_denied(self):
        other = self.source.parent / "link"
        other.symlink_to(self.source, target_is_directory=True)
        profile = mod.TrustedResticProfile(self.exe, self.hash, self.repo, self.secret, (other,), self.target)
        with self.assertRaises(mod.BackupHold):
            self.port(profile=profile)(object(), {"operation": "backup"})
    def test_nonzero_exit_not_accepted(self):
        port = self.port()
        port.runner = lambda argv, *, stop: (1, "")
        with self.assertRaises(mod.BackupHold):
            port(object(), {"operation": "backup"})
    def test_restic_must_emit_snapshot_summary(self):
        port = self.port()
        port.runner = lambda argv, *, stop: (0, "{}")
        with self.assertRaises(mod.BackupHold):
            port(object(), {"operation": "backup"})

if __name__ == "__main__":
    unittest.main()
