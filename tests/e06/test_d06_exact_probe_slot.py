"""D06: strict original NSIS slot check, with exactly one frozen unmanaged probe."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

OWNER = Path(__file__).resolve().parents[2] / "coordination/e06/t06_user_probe_slot.py"
spec = importlib.util.spec_from_file_location("nox_t06_user_probe_slot", OWNER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
verify_exact_probe_slot = module.verify_exact_probe_slot


class OriginalSlotProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "Programs" / "NOX HELION.__p01_previous"
        self.root.mkdir(parents=True)
        names = ["NOX.P01.Shell.exe", "Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"]
        names += [f"Assets/owner-{i}.bin" for i in range(10)]
        rows = []
        for name in names:
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            content = (name + " original").encode()
            file.write_bytes(content)
            rows.append({"path": name, "bytes": len(content),
                         "sha256": hashlib.sha256(content).hexdigest()})
        manifest = {"schema": "NOX_P01_PAYLOAD_SHA256_V1",
                    "entrypoint": "NOX.P01.Shell.exe", "runId": "D06-CI-01",
                    "version": "16.0.0", "files": rows}
        (self.root / "payload.sha256.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "nox-p01-owned.txt").write_bytes(b"NOXHELION.P01 V16\r\n")
        (self.root / "Uninstall.exe").write_bytes(b"MZ" + b"\0" * 1022)
        self.probe = self.root / "nox-g4-unmanaged-D06-CI-01.bin"
        self.bytes = b"NOX_G4_UNMANAGED_INSTALL_DATA_NOLOSS\\n"
        self.probe.write_bytes(self.bytes)
        st = self.probe.lstat()
        self.inode = (st.st_dev, st.st_ino)

    def verify(self):
        return verify_exact_probe_slot(self.root, self.probe.name, self.bytes,
                                       self.inode, self.base)

    def test_exact_backup_allow_one_frozen_unmanaged_file(self):
        result = self.verify()
        self.assertEqual(result["status"], "PASS_DIAGNOSTIC_ONLY")
        self.assertEqual(result["manifest_files_checked"], 12)
        self.assertFalse(result["release_accepted"])

    def test_extra_file_still_holds(self):
        (self.root / "foreign-extra.dat").write_bytes(b"bad")
        with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_FILE_HOLD"):
            self.verify()

    def test_owned_payload_sha_tamper_holds(self):
        (self.root / "Assets" / "owner-3.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "OWNED_SIZE_OR_PATH_HOLD|OWNED_SHA_HOLD"):
            self.verify()

    def test_same_bytes_replaced_inode_holds(self):
        newer = self.root / "replacement.tmp"
        newer.write_bytes(self.bytes)
        os.replace(newer, self.probe)
        with self.assertRaisesRegex(RuntimeError, "PROBE_IDENTITY_HOLD"):
            self.verify()

    def test_junction_or_symlink_hold(self):
        target = self.root / "Assets" / "owner-0.bin"
        target.unlink()
        try:
            target.symlink_to(self.root / "Assets" / "owner-1.bin")
        except OSError:
            self.skipTest("no symlink capability")
        with self.assertRaisesRegex(RuntimeError, "OWNED_SIZE_OR_PATH_HOLD"):
            self.verify()

    def test_metadata_missing_holds(self):
        (self.root / "Uninstall.exe").unlink()
        with self.assertRaisesRegex(RuntimeError, "NSIS_METADATA_HOLD"):
            self.verify()

    def test_duplicate_manifest_member_holds(self):
        path = self.root / "payload.sha256.json"
        raw = path.read_text(encoding="utf-8")
        raw = raw.replace('"version": "16.0.0"',
                          '"version": "16.0.0", "version": "16.0.0"')
        path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_JSON_HOLD"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
