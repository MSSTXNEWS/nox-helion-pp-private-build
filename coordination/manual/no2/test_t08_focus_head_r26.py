"""NOX V16 M2 R26: focused test PASS must be bound to exact current HEAD.

Use existing real Git-object fixture. Source-only QA, not native acceptance.
Run with python -m unittest test_t08_focus_head_r26 -v from this folder.
"""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from test_t08_real_git_objects_r19 import RealGitReadbackTests

SPEC = importlib.util.spec_from_file_location(
    "nox_gate_r26", Path(__file__).with_name("T08_R26_GATE_CANDIDATE.py"))
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class FocusedTestHeadR26(RealGitReadbackTests):
    def _check(self, test_receipt):
        p0proof = {"head_sha": self.head}
        handproof = {"source_head": self.head}
        p0 = {"head": self.head, "status": "PATCH_APPLIED",
              "receipt_blob": self.blob(json.dumps(p0proof).encode()),
              "focused_test_blob": self.blob(json.dumps(test_receipt).encode())}
        hand = {"head": self.head,
                "receipt_blob": self.blob(json.dumps(handproof).encode())}
        docs = {}
        for name in gate.DOCS:
            doc = {"doc": name, "revision_id": "readback-"+name+"-r26",
                   "incident_id": "ERR-T08-20261029-HOST50-SOURCELOCK-AUTOFIX-CHAIN-BROKEN",
                   "readback_pass": True}
            docs[name] = {"revision_id": doc["revision_id"],
                          "incident_id": doc["incident_id"],
                          "readback_receipt_blob": self.blob(json.dumps(doc).encode())}
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            return gate._verified_downstream(self.source, p0, hand, docs)

    def test_stale_pass_rejected(self):
        self.assertFalse(self._check({"status": "PASS", "head": "f"*40}))

    def test_empty_head_pass_rejected(self):
        self.assertFalse(self._check({"status": "PASS"}))

    def test_conflicting_head_aliases_rejected(self):
        self.assertFalse(self._check({"status": "PASS", "head": self.head,
                                      "source_head_sha": "f"*40}))

    def test_valid_same_head_pass_source_only(self):
        self.assertTrue(self._check({"status": "PASS", "head_sha": self.head}))

    def test_failed_same_head_rejected(self):
        self.assertFalse(self._check({"status": "FAIL", "head": self.head}))
