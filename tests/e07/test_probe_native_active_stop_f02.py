"""Source-level owner and no-loss regressions; NEVER native Windows E07 acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "coordination" / "e07"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("f02_stop_probe", SCRIPTS / "probe_native_active_stop.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class OwnedActiveStopPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root / "Programs" / "NOX HELION"
        self.install.mkdir(parents=True)
        self.backend = self.install / "Backend" / "NOX_HELION_PRIVATE_CANDIDATE.exe"
        self.backend.parent.mkdir()
        self.payload = b"original-installed-native-stdio-onehost"
        self.backend.write_bytes(self.payload)
        (self.install / "nox-p01-owned.txt").write_text("NOXHELION.P01 V16\n")
        self.manifest = self.install / "payload.sha256.json"
        self.manifest.write_text(json.dumps({
            "schema": "NOX_P01_PAYLOAD_SHA256_V1",
            "entrypoint": "NOX.P01.Shell.exe",
            "files": [{"path": "Backend/NOX_HELION_PRIVATE_CANDIDATE.exe",
                       "bytes": len(self.payload),
                       "sha256": hashlib.sha256(self.payload).hexdigest()}]
        }))
        self.runner = self.root / "runner-temp"
        self.runner.mkdir()
        self.scratch = self.runner / "nox-active-stop"
        self.scratch.mkdir()

    def test_exact_owned_fd_hashed_original_passes_source_preflight_only(self):
        digest = MOD.verify_owned_stop_backend(self.backend, self.install)
        self.assertEqual(digest, hashlib.sha256(self.payload).hexdigest())
        MOD.require_ephemeral_stop_dir(self.scratch, self.runner)
        self.assertFalse(MOD.PROTO == "")
        self.assertNotIn("release_accepted", MOD.verify_owned_stop_backend.__name__)

    def test_foreign_executable_outside_installed_original_rejected(self):
        other = self.root / "not-owned.exe"
        other.write_bytes(self.payload)
        with self.assertRaisesRegex(MOD.GateHold, "NOT_ORIGINAL_INSTALLED_BACKEND"):
            MOD.verify_owned_stop_backend(other, self.install)

    def test_differently_named_unowned_binary_rejected(self):
        other = self.backend.parent / "NOX_HELION_COPY.exe"
        other.write_bytes(self.payload)
        with self.assertRaisesRegex(MOD.GateHold, "NOT_ORIGINAL_INSTALLED_BACKEND"):
            MOD.verify_owned_stop_backend(other, self.install)

    def test_mutated_installed_backend_sha_refused(self):
        self.backend.write_bytes(b"X" + self.payload[1:])
        with self.assertRaisesRegex(MOD.GateHold, "OWNED_PAYLOAD_INTEGRITY_HOLD"):
            MOD.verify_owned_stop_backend(self.backend, self.install)

    def test_manifest_that_omits_backend_cannot_authorize_it(self):
        self.manifest.write_text(json.dumps({
            "schema": "NOX_P01_PAYLOAD_SHA256_V1",
            "entrypoint": "NOX.P01.Shell.exe",
            "files": [{"path": "Backend/OTHER.exe", "bytes": 1,
                       "sha256": "a" * 64}]
        }))
        with self.assertRaisesRegex(MOD.GateHold, "OWNED_PAYLOAD_INTEGRITY_HOLD"):
            MOD.verify_owned_stop_backend(self.backend, self.install)

    def test_external_or_shared_runner_root_rejected(self):
        other = self.root / "personal-data"
        other.mkdir()
        with self.assertRaisesRegex(MOD.GateHold, "OUTSIDE_RUNNER_HOLD"):
            MOD.require_ephemeral_stop_dir(other, self.runner)
        with self.assertRaisesRegex(MOD.GateHold, "OUTSIDE_RUNNER_HOLD"):
            MOD.require_ephemeral_stop_dir(self.runner, self.runner)

    def test_existing_native_data_is_never_reused(self):
        existing = self.scratch / "history.sqlite"
        existing.write_bytes(b"owner-history-preserve")
        with self.assertRaisesRegex(MOD.GateHold, "PREEXISTING_DATA_HOLD"):
            MOD.require_ephemeral_stop_dir(self.scratch, self.runner)
        self.assertEqual(existing.read_bytes(), b"owner-history-preserve")

    def test_reparse_scratch_not_followed(self):
        alias = self.runner / "junction-alias"
        try:
            alias.symlink_to(self.scratch, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(MOD.GateHold, "REPARSE_HOLD"):
            MOD.require_ephemeral_stop_dir(alias, self.runner)

    def test_reparse_installed_root_not_followed(self):
        alias = self.root / "root-alias"
        try:
            alias.symlink_to(self.install, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(MOD.GateHold, "REPARSE_HOLD"):
            MOD.verify_owned_stop_backend(alias / "Backend" / "NOX_HELION_PRIVATE_CANDIDATE.exe", alias)


if __name__ == "__main__":
    unittest.main()
