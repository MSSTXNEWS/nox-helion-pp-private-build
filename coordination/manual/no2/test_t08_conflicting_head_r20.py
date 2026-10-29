"""R20 independent QA regression of conflicting Git HEAD claims; source-only.
The test runs against current checkout's real T08 gate, with actual temporary Git blobs.
Requires prior independent helper test_t08_real_git_objects_r19.py in same folder.
"""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_t08_real_git_objects_r19 as helper

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("nox_t08_live", ROOT / "coordination/automation/t08/t08_autofix_closeout_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class ConflictingSourceIdentityR20(helper.RealGitReadbackTests):
    def test_matching_and_stale_heads_in_same_git_blob_fail_closed(self):
        p0 = {"head": self.head, "source_head": "a" * 40}
        hand = {"head_sha": self.head}
        p0_blob = self.blob(json.dumps(p0).encode())
        hand_blob = self.blob(json.dumps(hand).encode())
        docs = {}
        for name in gate.DOCS:
            doc = {"doc": name, "revision_id": "revision_" + name + "_valid",
                   "incident_id": "ERR-T08-20261029-HOST50-SOURCELOCK-AUTOFIX-CHAIN-BROKEN",
                   "readback_pass": True}
            docs[name] = {"revision_id": doc["revision_id"],
                          "incident_id": doc["incident_id"],
                          "readback_receipt_blob": self.blob(json.dumps(doc).encode())}
        p0.update({"receipt_blob": p0_blob, "status": "NO_CODE_BLOCKERS"})
        hand.update({"receipt_blob": hand_blob})
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            self.assertFalse(gate._verified_downstream(self.source, p0, hand, docs),
                             "One valid HEAD alias laundered a contradictory source_head")


if __name__ == "__main__":
    unittest.main()
