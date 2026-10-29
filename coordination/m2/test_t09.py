import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from t09_freeze_gate import evaluate

class TestT09SourceFreeze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nox-m2-source-")
        self.repo = Path(self.tmp.name)
        for args in (("init", "-q"), ("config", "user.name", "M2 QA"),
                     ("config", "user.email", "m2@example.invalid")):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        (self.repo / "README").write_text("local source-only fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "initial"], check=True, capture_output=True)
        guard = self.repo / "coordination/e06/t06_closeout_guard.py"
        guard.parent.mkdir(parents=True, exist_ok=True)
        guard.write_text("def decide(receipt, repo_root=None):\n"
                         "    return {'done': True, 'source_owner_accepted': True}\n",
                         encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "pin synthetic guard"],
                       check=True, capture_output=True)
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.manifest = self.add_blob(json.dumps({"head_sha": self.head,
                    "tree_sha": self.tree, "owner_acceptance": True}))
        self.manifest_hash = hashlib.sha256(self.git_bytes("cat-file", "blob", self.manifest)).hexdigest()
        self.evidence = {"source": {"head": self.head, "tree": self.tree,
                                  "manifest_blob": self.manifest},
                         "manifest_sha256": self.manifest_hash,
                         "t06_receipt_blob": "f" * 40,
                         "t08_receipt_blob": "e" * 40,
                         "original_lock_receipt_blob": "d" * 40}

    def tearDown(self): self.tmp.cleanup()
    def git_bytes(self,*args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True).stdout
    def git(self,*args): return self.git_bytes(*args).decode().strip()
    def add_blob(self,text):
        p=self.repo / "receipt.json"; p.write_text(text,encoding="utf-8")
        return self.git("hash-object", "-w", "receipt.json")

    def test_missing_git_tuple(self):
        self.assertEqual(evaluate(self.repo, {"source":{}})["status"],"FREEZE_HOLD")
    def test_fake_sha_strings_fail(self):
        x={"source":{"head":"a"*40,"tree":"b"*40,"manifest_blob":"c"*40}}
        self.assertEqual(evaluate(self.repo,x)["reason"],"CURRENT_HEAD_TREE_DRIFT")
    def test_manifest_sha256_mismatch(self):
        x=dict(self.evidence,manifest_sha256="a"*64)
        self.assertEqual(evaluate(self.repo,x)["reason"],"MANIFEST_RAW_SHA256_MISMATCH")
    def test_t06_owner_receipt_not_a_real_blob(self):
        self.assertEqual(evaluate(self.repo,self.evidence)["reason"],"GIT_OR_OWNER_RECEIPT_READBACK_FAILED")
    def test_boolean_flags_cannot_substitute_owner_receipts(self):
        x=dict(self.evidence,original_729_lock_pass=True,owner_patches_accepted=True,
               t06_accepted_head=self.head,t08_same_head=self.head)
        self.assertEqual(evaluate(self.repo,x)["status"],"FREEZE_HOLD")

    def test_dirty_t06_guard_refused_even_with_git_owner_blob(self):
        owner = {"head_sha": self.head, "tree_sha": self.tree,
                 "manifest_blob_sha": self.manifest, "owner_acceptance": True,
                 "source_no_loss_attested": True,
                 "criteria": {str(i): {} for i in range(8)}}
        self.evidence["t06_receipt_blob"] = self.add_blob(json.dumps(owner))
        guard = self.repo / "coordination/e06/t06_closeout_guard.py"
        guard.write_text("def decide(*args, **kwargs):\n"
                         "    return {'done': True, 'source_owner_accepted': True}\n",
                         encoding="utf-8")
        self.assertEqual(evaluate(self.repo, self.evidence)["reason"],
                         "T06_GUARD_WORKTREE_DRIFT")

    def test_clean_pinned_guard_still_requires_t08_proof(self):
        owner = {"head_sha": self.head, "tree_sha": self.tree,
                 "manifest_blob_sha": self.manifest, "owner_acceptance": True,
                 "source_no_loss_attested": True,
                 "criteria": {str(i): {} for i in range(8)}}
        self.evidence["t06_receipt_blob"] = self.add_blob(json.dumps(owner))
        self.assertEqual(evaluate(self.repo, self.evidence)["reason"],
                         "GIT_OR_OWNER_RECEIPT_READBACK_FAILED")

if __name__ == '__main__': unittest.main()
