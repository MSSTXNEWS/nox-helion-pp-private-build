"""Independent source-only proof tests for R18 T08 candidate.

The T06 owner closeout hook is STUBBED ONLY inside the temporary Git fixture.
These tests prove Git object lookup and fail-closed gating, NOT native acceptance.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

GATE = Path(__file__).with_name("T08_GUARD_PROPOSED_R18.py")
spec = importlib.util.spec_from_file_location("nox_t08_r18", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class RealGitReadbackTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="nox-git-proof-r19-")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        owner = self.root / "coordination/e06/t06_closeout_guard.py"
        owner.parent.mkdir(parents=True)
        owner.write_text(
            'def decide(receipt, repo_root=None):\n'
            '    return {"done": True, "source_owner_accepted": True,'
            ' "source_ready": False}\n', encoding="utf-8"
        )
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "qa@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "test fixture")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.manifest = b'{"immutable":true,"native_accepted":false}'
        manifest_blob = self.blob(self.manifest)
        self.owner = {
            "head_sha": self.head,
            "tree_sha": self.tree,
            "manifest_blob_sha": manifest_blob,
        }
        self.owner_blob = self.blob(json.dumps(self.owner).encode())
        self.source = {
            "head": self.head, "tree": self.tree,
            "manifest_sha256": hashlib.sha256(self.manifest).hexdigest(),
        }
        self.t06 = {"owner_receipt_blob": self.owner_blob}

        def read_git(*args):
            try:
                return self.git(*args)
            except subprocess.CalledProcessError as exc:
                raise ValueError("GIT_OBJECT_READBACK_FAILED") from exc

        self.git_reader = read_git

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True, capture_output=True, timeout=10
        ).stdout

    def blob(self, data):
        return subprocess.run(
            ["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
            input=data, check=True, capture_output=True, timeout=10
        ).stdout.decode().strip()

    def _proof(self):
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            return gate._verified_git_proof(self.source, self.t06)

    def test_real_git_receipt_validates_only_source(self):
        self.assertTrue(self._proof())

    def test_forged_owner_sha_fails(self):
        self.t06["owner_receipt_blob"] = "d" * 40
        self.assertFalse(self._proof())

    def test_changed_owner_head_fails(self):
        self.owner["head_sha"] = "a" * 40
        self.t06["owner_receipt_blob"] = self.blob(json.dumps(self.owner).encode())
        self.assertFalse(self._proof())

    def test_stale_head_fails(self):
        self.source["head"] = "a" * 40
        self.assertFalse(self._proof())

    def test_wrong_manifest_bytes_fail(self):
        self.source["manifest_sha256"] = "b" * 64
        self.assertFalse(self._proof())

    def test_nonexistent_manifest_blob_fails(self):
        self.owner["manifest_blob_sha"] = "e" * 40
        self.t06["owner_receipt_blob"] = self.blob(json.dumps(self.owner).encode())
        self.assertFalse(self._proof())

    def test_invalid_downstream_receipts_fail(self):
        fake = {"head": self.head, "receipt_blob": "f" * 40, "status": "NO_CODE_BLOCKERS"}
        handoff = {"head": self.head, "receipt_blob": "d" * 40}
        docs = {name: {"incident_id": "x", "revision_id": "revision_12345",
                       "readback_receipt_blob": "b" * 40} for name in gate.DOCS}
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            self.assertFalse(gate._verified_downstream(self.source, fake, handoff, docs))

    def test_unbounded_receipt_fails(self):
        huge = self.blob(b"x" * 262145)
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            with self.assertRaisesRegex(ValueError, "OUT_OF_BOUNDS"):
                gate._actual_json_blob(self.git_reader, huge)


if __name__ == "__main__":
    unittest.main()
