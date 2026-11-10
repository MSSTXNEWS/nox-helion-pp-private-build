"""Offline focused source-only T06 closeout tests; no EXE/NSIS/CI/E07."""
import contextlib
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("t06_closeout_guard", HERE / "t06_closeout_guard.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="t06-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "T06 Offline Test")
        self.git("config", "user.email", "t06@example.invalid")
        self.path = "Packages/P02/worker-python/source.py"
        p = self.root / self.path
        p.parent.mkdir(parents=True)
        p.write_text("source=1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture source")
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.src = self.git("rev-parse", "HEAD:" + self.path)
        self.choice = self.blob({"source_choice": True})
        self.criteria = {name: {"status": "HOLD", "owner": "T06",
                                "next_action": "EXACT_OWNER_RECEIPT"} for name in g.CRITERIA}
        self.criteria["base"] = {"status": "DONE", "evidence": {
            "canonical_head_sha": self.head, "source_choice_receipt": self.choice}}
        self.run_id = "NOX-V16-T06-20261029T174858MSK-R11"

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args],
                           capture_output=True, check=True)
        return p.stdout.decode().strip()

    def blob(self, obj):
        p = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
                           input=json.dumps(obj).encode(), capture_output=True, check=True)
        return p.stdout.decode().strip()

    def receipt(self, claim="HOLD"):
        return {"run_id": self.run_id, "claimed_status": claim,
                "criteria": self.criteria}

    def accept(self, name, source_path=None):
        path = source_path or self.path
        owner_id = g.OWNER_ID[name]
        owner_run = "OWNER-20261029-" + name
        owner = self.blob({"owner_id": owner_id, "run_id": owner_run, "source_path": path,
                           "preimage_sha": self.src, "postimage_sha": self.src, "approved": True})
        test = self.blob({"run_id": "TEST-" + name + "-20261029",
                          "owner_run_id": owner_run, "source_path": path,
                          "postimage_sha": self.src, "status": "PASS"})
        self.criteria[name] = {"status": "DONE", "owner_id": owner_id,
                               "evidence": {"source_path": path, "preimage_sha": self.src,
                                            "postimage_sha": self.src,
                                            "owner_receipt": {"blob_sha": owner, "run_id": owner_run},
                                            "test_receipt": {"blob_sha": test, "run_id": "TEST-" + name + "-20261029"}}}

    def test_fake_done_and_invalid_sha_rejected(self):
        out = g.decide(self.receipt("DONE"), self.root)
        self.assertEqual((out["completed"], out["progress_pct"]), (1, 12.5))
        self.assertTrue(out["premature_closeout_rejected"])
        self.accept("P02")
        self.criteria["P02"]["evidence"]["preimage_sha"] = "fake-nonblank-sha"
        self.assertEqual(g.decide(self.receipt("DONE"), self.root)["completed"], 1)

    def test_wrong_owner_and_unreadable_receipt_rejected(self):
        self.accept("P02")
        self.criteria["P02"]["owner_id"] = 1
        self.assertEqual(g.decide(self.receipt(), self.root)["completed"], 1)
        self.criteria["P02"]["owner_id"] = 2
        self.criteria["P02"]["evidence"]["test_receipt"]["blob_sha"] = "e" * 40
        self.assertEqual(g.decide(self.receipt(), self.root)["completed"], 1)

    def test_full_owner_source_accept_without_future_t10(self):
        # Each criterion needs a distinct current-tree source path and receipt.
        for i, name in enumerate(g.CRITERIA[1:], 1):
            path = "proof/path%d.py" % i
            f = self.root / path
            f.parent.mkdir(exist_ok=True)
            f.write_text("proof=%d\n" % i)
        self.git("add", ".")
        self.git("commit", "-qm", "owner paths")
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.src = self.git("rev-parse", "HEAD:" + self.path)
        for i, name in enumerate(g.CRITERIA[1:], 1):
            path = "proof/path%d.py" % i
            self.src = self.git("rev-parse", "HEAD:" + path)
            self.accept(name, path)
        self.src = self.git("rev-parse", "HEAD:" + self.path)
        manifest = self.blob({"head_sha": self.head, "tree_sha": self.tree,
                              "owner_acceptance": True})
        r = self.receipt("DONE")
        accept_blob = self.blob({"source_owner_accepted": True})
        noloss_blob = self.blob({"original_archive_729": "PRESERVED"})
        handoff_blob = self.blob({"handoff": "T09"})
        r.update(head_sha=self.head, tree_sha=self.tree,
                 manifest_blob_sha=manifest, owner_acceptance=True,
                 owner_acceptance_receipt_sha=accept_blob,
                 no_loss_receipt_sha=noloss_blob, source_no_loss_attested=True,
                 handoff_to_t09={"head_sha": self.head, "tree_sha": self.tree,
                                 "manifest_blob_sha": manifest,
                                 "receipt_sha": handoff_blob},
                 independent_source_qa=False)
        out = g.decide(r, self.root)
        self.assertTrue(out["done"])
        self.assertFalse(out["source_ready"])
        self.assertEqual(out["completed"], 8)
        r["owner_acceptance"] = False
        self.assertEqual(g.decide(r, self.root)["completed"], 7)
        r["owner_acceptance"] = True
        r["handoff_to_t09"]["tree_sha"] = "0" * 40
        self.assertEqual(g.decide(r, self.root)["completed"], 7)

    def test_real_runner_exit_calls_guard(self):
        # Exercise the EXISTING integration runner's --closeout-receipt path,
        # replacing unrelated owner component suites with local empty fixtures.
        evidence = self.root / "receipt.json"
        evidence.write_text(json.dumps(self.receipt("DONE")))
        src = HERE / "run_source_integrations_r13.py"
        sys.path.insert(0, str(HERE))
        self.addCleanup(lambda: sys.path.remove(str(HERE)))
        runner_spec = importlib.util.spec_from_file_location("t06_actual_runner", src)
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        p02, p03, pack, adapter = (self.root / x for x in
                                    ("P02", "P03", "PACK", "adapters"))
        for directory, filename in ((p02, "p02_native_ingress.py"),
                                    (p03, "p03_onehost_port.py"),
                                    (pack, "native_bridge.py"),
                                    (pack, "catalog.json"),
                                    (adapter, "test_g2_space_mobile.py")):
            directory.mkdir(exist_ok=True)
            (directory / filename).write_text("fixture\n")
        with mock.patch.multiple(runner, ROOT=self.root, P02=p02, P03=p03,
                                 PACK=pack, ADAPTER_TESTS=adapter, SUITES=(),
                                 decide_t06_closeout=lambda x:g.decide(x, self.root)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = runner.main(closeout_receipt=evidence)
        self.assertEqual(rc, 2)
        self.assertIn("premature_closeout_rejected", output.getvalue())
        self.assertIn("12.5", output.getvalue())

    def test_missing_criterion_or_run_rejected(self):
        r = self.receipt()
        del r["criteria"]["P05"]
        with self.assertRaises(ValueError): g.decide(r, self.root)
        r = self.receipt()
        r["run_id"] = "R"
        with self.assertRaises(ValueError): g.decide(r, self.root)


if __name__ == "__main__":
    unittest.main()
