"""Exact source runner→guard integration smoke; no EXE, NSIS, CI, or native host."""
import contextlib
import importlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import t06_closeout_guard as guard
import run_source_integrations_r13 as runner

class RunnerCloseoutSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        p02 = root / "p02"
        p03 = root / "p03"
        pack = root / "pack"
        e06 = root / "e06"
        for folder in (p02, p03, pack, e06):
            folder.mkdir()
        for path in (p02/"p02_native_ingress.py",
                     p03/"p03_onehost_port.py",
                     pack/"native_bridge.py",
                     pack/"catalog.json",
                     e06/"test_g2_space_mobile.py",
                     e06/"test_fake.py"):
            path.write_text("pass\n", encoding="utf-8")
        self.patches = [
            patch.object(runner, "ROOT", root),
            patch.object(runner, "P02", p02),
            patch.object(runner, "P03", p03),
            patch.object(runner, "PACK", pack),
            patch.object(runner, "ADAPTER_TESTS", e06),
            patch.object(runner, "SUITES", (("one owner suite", e06, "test_fake.py"),)),
            patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.root = root

    def receipt(self, approved=True):
        rows = {}
        for name in guard.CRITERIA:
            ev = ({"canonical_head_sha":"a"*40,"source_choice_receipt":"b"*40}
                  if name == "base" else {key:"c"*40 for key in guard.PROOF})
            rows[name] = {"status":"DONE","owner":"T06","owner_run_id":"OWNER-RUN-20261029",
                          "owner_approved":approved,"evidence":ev}
        return {"run_id":"SOURCE-OWNER-RUN","criteria":rows,
                "head_sha":"a"*40,"tree_sha":"b"*40,"manifest_blob_sha":"c"*40,
                "owner_acceptance_receipt_sha":"d"*40,"no_loss_receipt_sha":"e"*40,
                "owner_acceptance":True,"source_no_loss_attested":True,
                "handoff_to_t09":{"receipt_sha":"f"*40,"head_sha":"a"*40,
                                  "tree_sha":"b"*40,"manifest_blob_sha":"c"*40},
                "independent_source_qa":False}

    def test_incomplete_owner_proof_refused_by_actual_runner(self):
        p = self.root/"incomplete.json"
        p.write_text(json.dumps(self.receipt(approved=False)), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = runner.main(closeout_receipt=p)
        self.assertEqual(code, 2)
        self.assertIn("HOLD_INCOMPLETE", output.getvalue())

    def test_owner_source_done_precedes_independent_t10(self):
        p = self.root/"approved.json"
        p.write_text(json.dumps(self.receipt()), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = runner.main(closeout_receipt=p)
        self.assertEqual(code, 0)
        self.assertIn("T06_SOURCE_DONE", output.getvalue())
        self.assertNotIn("SOURCE_READY_PASS", output.getvalue())

if __name__ == "__main__":
    unittest.main()
