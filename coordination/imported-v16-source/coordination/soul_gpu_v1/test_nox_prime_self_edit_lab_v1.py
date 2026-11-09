"""SEAL-style candidate lab tests. Never execute model code, git writes or network."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from unittest.mock import patch
from types import SimpleNamespace
import nox_prime_self_edit_lab_v1 as lab

PATH="coordination/soul_gpu_v1/nox_unified_chat_v1.html"
DIFF=("diff --git a/"+PATH+" b/"+PATH+"\n"
      "--- a/"+PATH+"\n"
      "+++ b/"+PATH+"\n"
      "@@ -1 +1 @@\n-old\n+new\n")

class SelfEditTests(TestCase):
    def test_allowlist_rejects_safety_and_native(self):
        self.assertTrue(lab.allowable_path(PATH))
        for bad in ("C:/Windows/system.py","../../secret.py",".github/workflows/main.yml",
                    "coordination/soul_gpu_v1/nox_gpu_safe70.py",
                    "coordination/soul_gpu_v1/nox_s03_bridge.py",
                    "coordination/soul_gpu_v1/../bad.py"):
            self.assertFalse(lab.allowable_path(bad))
    def test_only_one_source_diff(self):
        self.assertTrue(lab.validate_diff(DIFF,PATH))
        with self.assertRaises(ValueError):
            lab.validate_diff(DIFF.replace("nox_unified_chat_v1.html","nox_gpu_safe70.py"),PATH)
        with self.assertRaises(ValueError):
            lab.validate_diff(DIFF+"+++ b/second.py\n",PATH)
        with self.assertRaises(ValueError):
            lab.validate_diff("Binary files differ",PATH)
    def test_candidate_not_applied(self):
        with TemporaryDirectory() as d:
            repo=Path(d)/"repo"
            repo.mkdir()
            (repo/".git").mkdir()
            root=Path(d)/"nox"
            with patch.object(lab,"_git",side_effect=["a"*40+"\n","old\n"]),\
                 patch.object(lab,"_generate",return_value={
                     "diff":DIFF,"summary":"small change","tests":["manual smoke"]}),\
                 patch.object(lab.subprocess,"run",return_value=SimpleNamespace(
                     returncode=0,stderr="",stdout="")) as run:
                result=lab.propose(repo,root,PATH,"Improve visual state display",model="qwen3:8b")
            data=json.loads(Path(result["candidate_path"]).read_text(encoding="utf-8"))
            self.assertEqual(data["source_sha"],"a"*40)
            self.assertFalse(data["applied_to_source"])
            self.assertFalse(data["code_executed"])
            self.assertEqual(data["git_apply_check"],"PASS")
            self.assertEqual(run.call_args.args[0][3:5],["apply","--check"])
    def test_invalid_objective_does_not_call_model(self):
        with TemporaryDirectory() as d:
            repo=Path(d)/"repo";repo.mkdir();(repo/".git").mkdir()
            with self.assertRaises(ValueError):
                lab.propose(repo,Path(d),"coordination/soul_gpu_v1/stop.py","123")
if __name__=="__main__":main()
