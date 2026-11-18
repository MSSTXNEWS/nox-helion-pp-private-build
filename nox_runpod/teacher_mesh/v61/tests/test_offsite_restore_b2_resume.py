"""B2: ciphertext/manifest integrity is not functional optimizer resume."""
import hashlib
import io
import json
import tarfile
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

from nox_runpod.teacher_mesh.v61.checkpoint_backup import REMOTE, verify_plaintext_tar, transport_retry_delay


def make_archive(names):
    records = []
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w:gz") as archive:
        for name in names:
            content = name.encode("utf-8")
            path = "NOX_CHECKPOINTS/" + name
            records.append({"path": path, "size_bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest()})
            info = tarfile.TarInfo(path)
            info.mode = 0o600
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        manifest = json.dumps(
            {"schema": "NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1",
             "origin_instance_id": 60509551,
             "files": records, "original_files_deleted": False},
            sort_keys=True, separators=(",", ":")).encode()
        meta = tarfile.TarInfo("RESTORE_MANIFEST.json")
        meta.mode = 0o600
        meta.size = len(manifest)
        archive.addfile(meta, io.BytesIO(manifest))
    return tar.getvalue()


class V61ResumeProofBoundary(unittest.TestCase):
    def test_generic_checkpoint_hash_pass_cannot_claim_optimizer_restore(self):
        names = [f"checkpoint_{index:02d}.pt" for index in range(12)]
        result = verify_plaintext_tar(make_archive(names))
        self.assertEqual(result["count"], 12)
        self.assertEqual(result["resume_name_hints"],
                         {"optimizer": False, "rng": False, "scaler": False})
        self.assertIs(result["functional_optimizer_restore_verified"], False)

    def test_named_states_still_require_functional_restore(self):
        names = ["optimizer.pt", "rng_state.pt", "scaler.pt"]
        names += [f"checkpoint_{index:02d}.pt" for index in range(9)]
        result = verify_plaintext_tar(make_archive(names))
        self.assertEqual(result["resume_name_hints"],
                         {"optimizer": True, "rng": True, "scaler": True})
        self.assertIs(result["functional_optimizer_restore_verified"], False)


class V61RemoteBoundedMemory(unittest.TestCase):
    def test_real_remote_tar_uses_chunked_hashing_without_path_read_bytes(self):
        # Run the actual embedded read-only remote script on an isolated fixture.
        # A subprocess-local guard turns any whole-file Path.read_bytes into FAIL.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for idx in range(10):
                (root / f"checkpoint_{idx:02d}.pt").write_bytes(bytes([idx]) * 4096)
            old_root = "root=Path('/root/nox')"
            self.assertEqual(REMOTE.count(old_root), 1)
            script = ("from pathlib import Path\n"
                      "def reject_read_bytes(*args, **kwargs):\n"
                      "    raise AssertionError('unbounded_checkpoint_read_bytes')\n"
                      "Path.read_bytes = reject_read_bytes\n"
                      + REMOTE.replace(old_root, f"root=Path({str(root)!r})"))
            result = subprocess.run([sys.executable, "-c", script],
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            checked = verify_plaintext_tar(result.stdout)
            self.assertEqual(checked["count"], 10)
            self.assertEqual(checked["total_bytes"], 40960)
            self.assertFalse(checked["functional_optimizer_restore_verified"])


class V61TransportRetryBoundary(unittest.TestCase):
    def test_only_bounded_readonly_timeout_may_retry(self):
        self.assertEqual(transport_retry_delay('SSH_NETWORK_TIMEOUT', 0), 10)
        self.assertEqual(transport_retry_delay('SSH_NETWORK_TIMEOUT', 1), 30)
        self.assertIsNone(transport_retry_delay('SSH_NETWORK_TIMEOUT', 2))
        for status in ('CHECKPOINT_CHANGED_DURING_STREAM',
                       'CHECKPOINT_TOTAL_SIZE_LIMIT', 'CHECKPOINT_FILE_COUNT',
                       'SSH_AUTH_DENIED', 'REMOTE_PYTHON', 'OTHER'):
            self.assertIsNone(transport_retry_delay(status, 0))
        self.assertIsNone(transport_retry_delay('SSH_NETWORK_TIMEOUT', -1))
        self.assertIsNone(transport_retry_delay('SSH_NETWORK_TIMEOUT', True))


if __name__ == "__main__":
    unittest.main()
