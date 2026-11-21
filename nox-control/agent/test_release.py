import os, tempfile, unittest
from ._testutil import mkcfg, make_repo, sh, touch
from .release import Release, Sandbox
from .tools.approvals import Approvals


class RelBase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.repo = make_repo(os.path.join(self.tmp, "repo"))
        self.cfg = mkcfg(self.tmp, NOX_AGENT_HEALTH_CHECKS="2")
        self.sb = Sandbox(self.cfg)
        self.health = [True]
        self.deploys = []

    def branch_with(self, files, name="feat", delete=()):
        s = self.sb.create(name)
        for p, c in files.items(): touch(os.path.join(s["path"], p), c)
        for p in delete: os.remove(os.path.join(s["path"], p))
        sh(s["path"], "git", "add", "-A"); sh(s["path"], "git", "commit", "-q", "-m", "w")
        return s

    def rel(self, judge_ok=True, tests=None, **kw):
        tests = tests or (lambda wd: __import__("agent.tools.testing", fromlist=["x"]).run_tests(wd, self.cfg))
        return Release(self.cfg, tests_fn=tests, judge_fn=lambda t, d, r: {"ok": judge_ok, "reasons": ["r"]}, health_fn=lambda: self.health.pop(0) if len(self.health) > 1 else self.health[0],
                       deploy_fn=lambda: (self.deploys.append(1) or {"ok": True}), approvals=Approvals(self.cfg.approvals_file), sleep=lambda s: None, **kw)

    def head(self): return sh(self.repo, "git", "rev-parse", "HEAD")


class TestSandbox(RelBase):
    def test_worktree_branch(self):
        s = self.sb.create("Моя задача fix", "T-1")
        self.assertTrue(s["branch"].startswith("nox/")); self.assertTrue(os.path.isdir(s["path"]))
        self.assertEqual(sh(s["path"], "git", "rev-parse", "--abbrev-ref", "HEAD"), s["branch"])
        self.assertTrue(self.sb.create("Моя задача fix", "T-1")["reused"])
        self.sb.remove(s["path"]); self.assertFalse(os.path.exists(s["path"]))


class TestRelease(RelBase):
    def test_happy_merge(self):
        s = self.branch_with({"nox-control/agent/feature.py": "X = 1\n"})
        before = self.head()
        r = self.rel().deploy(s["branch"], s["path"], "feat")
        self.assertEqual(r["status"], "merged", r)
        self.assertNotEqual(self.head(), before)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "nox-control/agent/feature.py")))
        self.assertEqual(self.deploys, [1])

    def test_red_tests_refused(self):
        s = self.branch_with({"nox-control/agent/test_bad.py": "import unittest\nclass B(unittest.TestCase):\n    def test_b(self): self.fail('x')\n"})
        before = self.head()
        r = self.rel().deploy(s["branch"], s["path"], "bad")
        self.assertEqual((r["status"], self.head()), ("rejected", before)); self.assertIn("тесты", r["reason"])

    def test_judge_no_refused(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        before = self.head()
        r = self.rel(judge_ok=False).deploy(s["branch"], s["path"], "f")
        self.assertEqual((r["status"], self.head()), ("rejected", before))
        r2 = Release(self.cfg, tests_fn=lambda wd: {"ok": True}, judge_fn=None, approvals=Approvals(self.cfg.approvals_file)).deploy(s["branch"], s["path"], "f")
        self.assertEqual(r2["status"], "rejected"); self.assertIn("судья", r2["reason"])
        r3 = Release(self.cfg, tests_fn=lambda wd: {"ok": True}, judge_fn=lambda *a: {"ok": "yes"}, approvals=Approvals(self.cfg.approvals_file)).deploy(s["branch"], s["path"], "f")
        self.assertEqual(r3["status"], "rejected")        # только строго True

    def test_health_fail_rolls_back(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        before = self.head()
        self.health = [True, True, False]      # до выкатки ок, первая проверка после ок, вторая упала
        r = self.rel().deploy(s["branch"], s["path"], "f")
        self.assertEqual(r["status"], "rolled_back", r)
        self.assertEqual(self.head(), before); self.assertFalse(os.path.exists(os.path.join(self.repo, "nox-control/agent/f.py")))
        self.assertEqual(len(self.deploys), 2)          # выкатка и повторная выкатка после отката

    def test_baseline_red_refuses(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        self.health = [False]
        r = self.rel().deploy(s["branch"], s["path"], "f")
        self.assertEqual(r["status"], "refused")

    def test_rollback_with_foreign_commit_uses_revert(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        rel = self.rel()
        pre = self.head()
        sh(self.repo, "git", "merge", "--no-ff", "-q", "-m", "m", s["branch"]); merged = self.head()
        touch(os.path.join(self.repo, "other.txt"), "o"); sh(self.repo, "git", "add", "-A"); sh(self.repo, "git", "commit", "-q", "-m", "foreign")
        rb = rel.rollback(merged, pre)
        self.assertTrue(rb["ok"]); self.assertEqual(rb["how"], "revert")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "other.txt"))); self.assertFalse(os.path.exists(os.path.join(self.repo, "nox-control/agent/f.py")))

    def test_stop_before_merge(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        touch(self.cfg.stop_file)
        before = self.head()
        self.assertEqual(self.rel().deploy(s["branch"], s["path"], "f")["status"], "stopped"); self.assertEqual(self.head(), before)

    def test_stop_after_merge_rolls_back(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        before = self.head()
        rel = self.rel()
        orig = rel.deploy_fn
        rel.deploy_fn = lambda: (touch(self.cfg.stop_file), orig())[1]       # STOP приходит во время выкатки
        r = rel.deploy(s["branch"], s["path"], "f")
        self.assertEqual(r["status"], "rolled_back"); self.assertEqual(self.head(), before)

    def test_deletion_needs_owner(self):
        touch(os.path.join(self.repo, "old.txt"), "o"); sh(self.repo, "git", "add", "-A"); sh(self.repo, "git", "commit", "-q", "-m", "old")
        s = self.branch_with({}, delete=["old.txt"])
        before = self.head()
        rel = self.rel()
        r = rel.deploy(s["branch"], s["path"], "del")
        self.assertEqual(r["status"], "awaiting_owner", r); self.assertEqual(self.head(), before)
        Approvals(self.cfg.approvals_file).decide(r["approval_id"], "approved")
        r2 = rel.deploy(s["branch"], s["path"], "del")
        self.assertEqual(r2["status"], "merged", r2); self.assertFalse(os.path.exists(os.path.join(self.repo, "old.txt")))

    def test_protected_module_needs_owner(self):
        s = self.branch_with({"nox-control/agent/release.py": "# hack\n"})
        self.assertEqual(self.rel().deploy(s["branch"], s["path"], "p")["status"], "awaiting_owner")

    def test_no_merge_mode_and_bad_branch(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        self.cfg.merge = False
        before = self.head()
        self.assertEqual(self.rel().deploy(s["branch"], s["path"], "f")["status"], "ready"); self.assertEqual(self.head(), before)
        self.assertEqual(self.rel().deploy("main", self.repo, "x")["status"], "refused")

    def test_dirty_worktree_and_live_repo(self):
        s = self.branch_with({"nox-control/agent/f.py": "X=1\n"})
        touch(os.path.join(s["path"], "dirty.txt"))
        self.assertEqual(self.rel().deploy(s["branch"], s["path"], "f")["status"], "refused")
        os.remove(os.path.join(s["path"], "dirty.txt"))
        touch(os.path.join(self.repo, "README.md"), "changed")
        self.assertEqual(self.rel().deploy(s["branch"], s["path"], "f")["status"], "refused")


if __name__ == "__main__":
    unittest.main()
