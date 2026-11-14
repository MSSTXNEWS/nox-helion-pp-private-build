"""Offline-only Executor #2 contract tests. Mock receipts are NOT live evidence."""
import copy
import unittest
from nox_runpod.teacher_mesh.v39.native_control import Scope
from nox_runpod.teacher_mesh.v49.e2_handoff import (
    PLAN, MASTER, _load, validate_plan, prepare_signed_reads, audit_native_read_receipts,
)
from nox_runpod.teacher_mesh.v49.onehost_bridge import RECEIPT_SCHEMA, sign_request, digest

TEST_KEY = b"offline-e2-tests-not-production-key-32bytes"


class Executor2HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = _load(PLAN)
        cls.master = _load(MASTER)
        cls.scope = Scope("NOX_OWNER", "owner", "main")

    def new_inbox(self, ids=("R60-021",)):
        return prepare_signed_reads(self.plan, self.master, list(ids),
            scope=self.scope, secret=TEST_KEY, issued_at=1700000000,
            nonce="aabbccddeeff0011")

    def mock_receipt(self, request):
        untrusted = {k:v for k,v in request.items() if k != "signature"}
        x = {
            "schema":RECEIPT_SCHEMA, "request_id":request["request_id"],
            "action":request["action"], "request_sha256":digest(untrusted),
            "state":"READ_ONLY_FROM_NATIVE_ONEHOST", "native_readback":True,
            "independent_verified":False,"s03_durable":True,
            "performed":False,"data_sha256":"f"*64,
        }
        x["receipt_signature"]=sign_request(x,TEST_KEY)
        return x

    def ledger(self, rows):
        return {"schema":"NOX_ONEHOST_BRIDGE_RECEIPTS_V1",
                "instance_id":60509551, "receipts":rows}

    def test_real_60_master_and_exact_30_e2_tasks(self):
        m=validate_plan(self.plan,self.master)
        self.assertEqual(len(m),30)
        self.assertEqual(set(m),{f"R60-{i:03d}" for i in list(range(21,41))+list(range(51,61))})
        self.assertEqual(m["R60-021"],"nox.training.status")
        self.assertEqual(m["R60-052"],"server.gpus")

    def test_signatures_are_compatible_with_v49_bridge(self):
        x=self.new_inbox(("R60-021","R60-022"))
        self.assertEqual(x["schema"],"NOX_ONEHOST_BRIDGE_INBOX_V1")
        for req in x["requests"]:
            self.assertEqual(req["signature"],sign_request(req,TEST_KEY))
            self.assertEqual(req["parameters"],{})
            self.assertEqual(req["expires_at"]-req["issued_at"],180)

    def test_no_new_scheduler_or_native_completion(self):
        inbox=self.new_inbox()
        r=self.mock_receipt(inbox["requests"][0])
        a=audit_native_read_receipts(inbox,self.ledger([r]),TEST_KEY)
        self.assertEqual(a["state"],"SIGNED_S03_NATIVE_OBSERVATIONS_ONLY")
        self.assertEqual(a["signed_read_receipts"],1)
        self.assertEqual(a["queue_enqueued"],0)
        self.assertFalse(a["weights_changed"])
        self.assertFalse(a["optimizer_steps_verified"])
        self.assertEqual(a["native_task_ids"],[])

    def test_unsigned_or_tampered_receipt_never_passes(self):
        inbox=self.new_inbox()
        r=self.mock_receipt(inbox["requests"][0])
        r["state"]="COMPLETED"
        self.assertEqual(audit_native_read_receipts(inbox,self.ledger([r]),TEST_KEY)["signed_read_receipts"],0)

    def test_repeated_receipt_not_accepted_as_new(self):
        inbox=self.new_inbox()
        r=self.mock_receipt(inbox["requests"][0])
        self.assertEqual(audit_native_read_receipts(inbox,self.ledger([r,r]),TEST_KEY)["signed_read_receipts"],0)

    def test_no_owner_signer_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"HOLD_OWNER_BRIDGE_SIGNING_KEY"):
            prepare_signed_reads(self.plan,self.master,["R60-021"],
                scope=self.scope,secret=b"bad",issued_at=1700000000,nonce="aabbccddeeff0011")
        self.assertEqual(audit_native_read_receipts({}, {}, b"bad")["state"],"HOLD_OWNER_KEY")

    def test_no_owner1_or_unbounded_requests(self):
        with self.assertRaises(ValueError):self.new_inbox(("R60-001",))
        with self.assertRaises(ValueError):self.new_inbox(tuple(f"R60-{i:03d}" for i in range(21,30)))
        with self.assertRaises(ValueError):self.new_inbox(("R60-021","R60-021"))

    def test_master_false_registration_rejected(self):
        m=copy.deepcopy(self.master)
        m["registered_count"]=1
        with self.assertRaisesRegex(ValueError,"HOLD_LIVE_QUEUE_CHANGED"):
            validate_plan(self.plan,m)
        m=copy.deepcopy(self.master)
        m["tasks"][20]["verified"]=True
        with self.assertRaisesRegex(ValueError,"HOLD_FALSE_REGISTRATION"):
            validate_plan(self.plan,m)

    def test_wrong_scope_and_action_rejected(self):
        m=copy.deepcopy(self.plan)
        m["tasks"][0]["read_action"]="nox.forge.distill.enqueue"
        with self.assertRaisesRegex(ValueError,"HOLD_READ_ALLOWLIST"):
            validate_plan(m,self.master)
        m=copy.deepcopy(self.plan)
        m["tasks"][0]["task_id"]="R60-001"
        with self.assertRaisesRegex(ValueError,"HOLD_E2_OWNER"):
            validate_plan(m,self.master)


if __name__=="__main__":
    unittest.main()
