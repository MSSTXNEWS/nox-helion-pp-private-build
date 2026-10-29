"""One focused regression for T06 immutable Git receipt verifier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).with_name("t06_owner_receipt_same_head_gate_r23.py")
spec=importlib.util.spec_from_file_location("nox_r23_owner_gate",SCRIPT)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class OwnerReceiptGateR23(unittest.TestCase):
    def test_unsafe_owner_paths_are_rejected(self):
        # Source-only: Windows reparse-style separators and embedded NUL must
        # not reach Git show / receipt path matching on any host platform.
        self.assertFalse(gate.safe_path(r"Packages\P04\model.py"))
        self.assertFalse(gate.safe_path("Packages/P04/model\x00.py"))
        self.assertFalse(gate.safe_path("Packages/../secret"))
        self.assertFalse(gate.safe_path("/absolute/path"))
        self.assertTrue(gate.safe_path("Packages/P04/model.py"))

    def test_true_git_receipts_do_not_claim_native_and_stale_receipts_fail(self):
        rows={}
        files={}
        for owner,receipt in gate.RECEIPTS.items():
            path="test/"+owner+".source"
            if owner=="P01":
                items=[{"path":path,"git_blob_sha1":"a"*40}]
                rows[receipt]={"parts":items}
            elif owner=="P02":
                body=b"actual-utf8-owner-source"
                items=[{"path":path,"sha256":hashlib.sha256(body).hexdigest()}]
                files[path]=body
                rows[receipt]={"paths":items}
            else:
                items=[{"path":path,"post_git_blob_sha1":"a"*40}]
                rows[receipt]={"files":items}
        mapping="proposals/NOX-PACK01-50/owner-binding-map.json"
        rows[mapping]={"routes":[{"routeId":"chat.voice","sourceBinding":"owner.py"},
                                  {"routeId":"training.start","sourceBinding":None}],
                       "remainingNativeBlockers":[{"routeId":"chat.voice"},
                                                  {"routeId":"training.start"}]}
        def fetch(_head,path):
            if path in rows:return json.dumps(rows[path]).encode()
            return files[path]
        def blob(_head,path):
            return "a"*40 if path in rows or path.startswith("test/") else None
        with patch.object(gate,"read_at",side_effect=fetch),patch.object(
                gate,"blob_at",side_effect=blob):
            out=gate.audit("b"*40)
            self.assertTrue(out["all_source_receipts_match"])
            self.assertIs(out["source_ready"],False)
            self.assertIs(out["owner_qa_accepted"],False)
            self.assertEqual(out["native_windows"],"NOT_RUN")
            self.assertEqual(len(out["host50"]["native_pending"]),2)
            with patch.object(gate,"blob_at",side_effect=lambda h,p:(
                    "c"*40 if p=="test/P05.source" else blob(h,p))):
                stale=gate.audit("b"*40)
            self.assertFalse(stale["all_source_receipts_match"])
            self.assertEqual(stale["owners"]["P05"]["matched"],0)
            self.assertEqual(stale["status"],"STALE_OWNER_RECEIPTS_NATIVE_NOT_ACCEPTED")


if __name__=="__main__":
    unittest.main()
