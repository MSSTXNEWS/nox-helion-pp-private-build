"""B2: ciphertext/manifest integrity is not functional optimizer resume."""
import hashlib
import io
import json
import tarfile
import unittest

from nox_runpod.teacher_mesh.v61.checkpoint_backup import verify_plaintext_tar


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


if __name__ == "__main__":
    unittest.main()
