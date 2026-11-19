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

from nox_runpod.teacher_mesh.v61.checkpoint_backup import (REMOTE, verify_plaintext_tar,
    verify_plaintext_tar_stream, verify, transport_retry_delay,
    classify_ssh_timeout, publish_verified_backup, run)
from unittest.mock import patch


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


class V61StreamingDecryptRegression(unittest.TestCase):
    def test_archive_stream_does_not_read_all_plaintext_or_write_tempfile(self):
        archive=make_archive(["optimizer.pt","rng_state.pt","scaler.pt"] +
                             [f"checkpoint_{i:02d}.pt" for i in range(9)])
        class BoundedSource(io.BytesIO):
            def read(self,n=-1):
                if n<=0 or n>1048576:
                    raise AssertionError("unbounded_stream_read")
                return super().read(n)
        verified=verify_plaintext_tar_stream(BoundedSource(archive))
        self.assertEqual(verified["plaintext_sha256"],hashlib.sha256(archive).hexdigest())
        self.assertEqual(verified["count"],12)
        self.assertEqual(verified["resume_name_hints"],
                         {"optimizer":True,"rng":True,"scaler":True})
        self.assertIs(verified["functional_optimizer_restore_verified"],False)

    def test_actual_verify_uses_pipe_not_capture_output(self):
        archive=make_archive([f"checkpoint_{i:02d}.pt" for i in range(12)])
        class StubProcess:
            def __init__(self):
                self.stdout=io.BytesIO(archive)
            def poll(self):
                return 0
            def wait(self,timeout=None):
                return 0
        with patch("nox_runpod.teacher_mesh.v61.checkpoint_backup.subprocess.Popen",
                   return_value=StubProcess()) as create:
            verified=verify(Path("unused.age"),Path("unused.key"))
        self.assertEqual(verified["plaintext_sha256"],hashlib.sha256(archive).hexdigest())
        self.assertEqual(verified["count"],12)
        self.assertNotIn("capture_output",create.call_args.kwargs)
        self.assertEqual(create.call_args.kwargs["stdout"],subprocess.PIPE)

    def test_stream_rejects_manifest_missing(self):
        with self.assertRaisesRegex(RuntimeError,"HOLD_TAR_MEMBER_COUNT"):
            verify_plaintext_tar_stream(io.BytesIO(make_archive(
                [f"checkpoint_{i:02d}.pt" for i in range(9)])))


class V61TransportRetryBoundary(unittest.TestCase):
    def test_only_pre_execution_connect_timeout_may_retry(self):
        preexec='SSH_CONNECT_TIMEOUT_PRE_EXEC'
        self.assertEqual(transport_retry_delay(preexec, 0), 10)
        self.assertEqual(transport_retry_delay(preexec, 1), 30)
        self.assertIsNone(transport_retry_delay(preexec, 2))
        for status in ('CHECKPOINT_CHANGED_DURING_STREAM',
                       'CHECKPOINT_TOTAL_SIZE_LIMIT', 'CHECKPOINT_FILE_COUNT',
                       'SSH_AUTH_DENIED', 'REMOTE_PYTHON', 'OTHER',
                       'SSH_NETWORK_TIMEOUT', 'SSH_TIMEOUT_REMOTE_STATE_UNKNOWN'):
            self.assertIsNone(transport_retry_delay(status, 0))
        self.assertIsNone(transport_retry_delay(preexec, -1))
        self.assertIsNone(transport_retry_delay(preexec, True))

    def test_ambiguous_timeout_must_not_replay_remote_export(self):
        connect=b'ssh: connect to host example port 22: Connection timed out'
        self.assertEqual(classify_ssh_timeout(255, connect),
                         'SSH_CONNECT_TIMEOUT_PRE_EXEC')
        for rc, stderr in [
            (1, connect),
            (255, b'Connection to example timed out during key exchange'),
            (255, b'remote checkpoint exporter timed out'),
            (0, b'checkpoint timed out after writing tar'),
        ]:
            self.assertEqual(classify_ssh_timeout(rc, stderr),
                             'SSH_TIMEOUT_REMOTE_STATE_UNKNOWN')
        self.assertIsNone(classify_ssh_timeout(255,b'permission denied'))



class V61PublishedArtifactPreservation(unittest.TestCase):
    def test_existing_final_holds_before_owner_keys_or_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            final=root/'prior.age'
            receipt=root/'prior.json'
            final.write_bytes(b'preserved-owner-backup')
            receipt.write_text('{"sha":"old"}')
            with patch('nox_runpod.teacher_mesh.v61.checkpoint_backup.FINAL', final), \
                 patch('nox_runpod.teacher_mesh.v61.checkpoint_backup.RECEIPT', receipt), \
                 patch('nox_runpod.teacher_mesh.v61.checkpoint_backup.v60.existing_owner_recipient', side_effect=AssertionError('owner_credentials_touched')):
                with self.assertRaisesRegex(RuntimeError,'HOLD_V61_EXISTING_PUBLISHED_ARTIFACT'):
                    run()
            self.assertEqual(final.read_bytes(),b'preserved-owner-backup')
            self.assertEqual(receipt.read_text(),'{"sha":"old"}')


    def test_existing_verified_ciphertext_is_never_replaced_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            final=root/"checkpoint.age"
            receipt_path=root/"receipt.json"
            candidate=root/"checkpoint.age.pending"
            final.write_bytes(b"previous-encrypted-checkpoint")
            receipt_path.write_text('{"old":true}')
            candidate.write_bytes(b"new-candidate")
            with self.assertRaisesRegex(RuntimeError,"HOLD_V61_EXISTING_PUBLISHED_ARTIFACT"):
                publish_verified_backup(candidate,final,receipt_path,{"new":True})
            self.assertEqual(final.read_bytes(),b"previous-encrypted-checkpoint")
            self.assertEqual(receipt_path.read_text(),'{"old":true}')
            self.assertEqual(candidate.read_bytes(),b"new-candidate")

    def test_interleaved_publisher_cannot_replace_prior_ciphertext(self):
        # Simulate a rival publisher creating the destination after the
        # initial exists() check, immediately before the atomic link.
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            final=root/"checkpoint.age"
            receipt_path=root/"receipt.json"
            candidate=root/"checkpoint.age.pending"
            candidate.write_bytes(b"new-candidate")
            original_link=os.link

            def rival_wins(source,destination,*args,**kwargs):
                if Path(destination)==final:
                    final.write_bytes(b"rival-published-ciphertext")
                return original_link(source,destination,*args,**kwargs)

            with patch("nox_runpod.teacher_mesh.v61.checkpoint_backup.os.link",
                       side_effect=rival_wins):
                with self.assertRaisesRegex(RuntimeError,"HOLD_V61_PUBLISH_RACE"):
                    publish_verified_backup(candidate,final,receipt_path,{"new":True})
            self.assertEqual(final.read_bytes(),b"rival-published-ciphertext")
            self.assertFalse(receipt_path.exists())
            self.assertTrue(candidate.exists())
            self.assertFalse(list(root.glob("receipt.json.pending.*")))

    def test_verified_candidate_publishes_with_corresponding_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            final=root/"checkpoint.age"
            receipt_path=root/"receipt.json"
            candidate=root/"checkpoint.age.pending"
            candidate.write_bytes(b"candidate-ciphertext")
            publish_verified_backup(candidate,final,receipt_path,{"archive_hash_integrity_verified":True})
            self.assertFalse(candidate.exists())
            self.assertEqual(final.read_bytes(),b"candidate-ciphertext")
            self.assertTrue(json.loads(receipt_path.read_text())["archive_hash_integrity_verified"])
            self.assertFalse((root/"receipt.json.pending").exists())


if __name__ == "__main__":
    unittest.main()
