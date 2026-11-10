"""A6: security contract tests, existing source only; no native E07 claim."""
import unittest
from src.nox_selfbuilder.worms import WormHold
from src.nox_selfbuilder.growth_sandbox import (
    accept_sandbox_receipt, bind_growth_sandbox, compose_experiment)
from src.nox_selfbuilder.test_growth_sandbox import (
    proposal, green_checks, sandbox_attest, ARTIFACT)

class A6ReceiptFence(unittest.TestCase):
    def setup_ticket(self):
        candidate=proposal()
        ticket=compose_experiment(candidate,
            owner_policy={"native_signed": True, "allow_disposable_sandbox": True},
            source_checks=green_checks(), artifact_sha256=ARTIFACT,
            sandbox_attestation=sandbox_attest())
        receipt={"candidate_id":ticket["candidate_id"],"artifact_sha256":ARTIFACT,
            "isolation_verified":True,"environment_destroyed":True,
            "network_disabled":True,"host_written":False,
            "passed_tests":4,"failed_tests":0}
        return ticket,receipt

    def test_valid_source_receipt_stays_review_only(self):
        ticket,receipt=self.setup_ticket()
        result=accept_sandbox_receipt(ticket,receipt)
        self.assertEqual(result["state"],"SANDBOX_TESTED_AWAITING_I0")
        self.assertFalse(result["production_merged"])
        for name in ("source_head","candidate_sha256","artifact_sha256"):
            self.assertEqual(result[name],ticket[name])

    def test_unsafe_ticket_cannot_be_revived(self):
        ticket,receipt=self.setup_ticket()
        cases={"state":"HOLD","network_disabled":False,"host_execution":True,
            "host_mutation_allowed":True,"live_install_allowed":True,
            "weights_updated":True,"time_limit_seconds":900,
            "memory_limit_mib":4096,"source_head":"bad",
            "candidate_sha256":"bad","artifact_sha256":"bad"}
        for k,v in cases.items():
            with self.subTest(field=k),self.assertRaises(WormHold):
                accept_sandbox_receipt({**ticket,k:v},receipt)

    def test_review_cannot_switch_candidate_or_artifact(self):
        ticket,receipt=self.setup_ticket()
        review=accept_sandbox_receipt(ticket,receipt)
        diff={"schema":"NOX-GROWTH-DIFF-TICKET-v1","candidate_id":ticket["candidate_id"],
            "source_head":ticket["source_head"],"ticket_sha256":"a"*64,
            "post_sha256":ticket["artifact_sha256"],"pre_sha256":"b"*64,
            "path":"src/nox_selfbuilder/example.py","pre_blob_sha1":"c"*40,
            "post_blob_sha1":"d"*40,"diff_sha256":"e"*64}
        for name,bad in (("source_head","f"*40),
                         ("candidate_sha256","f"*64),("artifact_sha256","f"*64)):
            calls=[]
            with self.subTest(field=name),self.assertRaises(WormHold):
                bind_growth_sandbox(diff,ticket,{**review,name:bad},
                    session="native",native_verify=lambda *_:calls.append(True) or True)
            self.assertEqual(calls,[])
        result=bind_growth_sandbox(diff,ticket,review,
            session="native",native_verify=lambda *_:True)
        self.assertEqual(result["state"],"WAIT_NATIVE_OWNER_APPROVAL")

if __name__=="__main__": unittest.main()
