"""A1: real native owner callback exceptions must HOLD, never fake FirstBoot PASS.
No network, model download, synthetic consent or installed E07.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))
from test_firstboot_coordinator import State, NOW, policy


def fail(*_args, **_kwargs):
    raise OSError("private native provider path / key MUST NEVER LEAK")


class FirstBootNativeCallbackFailures(unittest.TestCase):
    def check_hold(self, receipt, reason):
        self.assertEqual(receipt["status"],"HOLD")
        self.assertEqual(receipt["reason"],reason)
        self.assertEqual(receipt["downloaded"],0)
        self.assertFalse(receipt["release_accepted"])
        self.assertNotIn("private native",repr(receipt))

    def test_policy_exception_stops_before_any_owner_write(self):
        owner=State()
        owner.app.callbacks=replace(owner.app.callbacks, policy=fail)
        self.check_hold(owner.app.run("S",now=NOW),"NATIVE_FIRSTBOOT_CALLBACK_EXCEPTION")
        self.assertEqual(owner.persisted,[])
        self.assertEqual(owner.calls,[])

    def test_installed_snapshot_exception_never_claims_already_present(self):
        owner=State()
        owner.app.callbacks=replace(owner.app.callbacks, installed=fail)
        self.check_hold(owner.app.run("S",now=NOW),"NATIVE_FIRSTBOOT_CALLBACK_EXCEPTION")
        self.assertEqual(owner.calls,[])

    def test_unavailable_stop_witness_is_never_treated_as_consent(self):
        owner=State()
        owner.app.callbacks=replace(owner.app.callbacks, stopped=fail)
        result=owner.app.run("S",now=NOW)
        self.assertEqual(result["status"],"STOPPED")
        self.assertEqual(owner.calls,[])

    def test_s03_intent_exception_cannot_queue_optional_models(self):
        owner=State()
        owner.app.callbacks=replace(owner.app.callbacks, persist=fail)
        self.check_hold(owner.app.run("S",now=NOW),"NATIVE_S03_INTENT_READBACK_REQUIRED")
        self.assertEqual(owner.calls,[])

    def test_s03_ingest_exception_requires_readback_and_no_queue(self):
        owner=State()
        digest="f"*64
        owner.p=policy(allow_local_knowledge_ingest=True,
                       reviewed_local_artifacts={digest:{"rights_verified":True,
                                                         "content_safe_for_s03":True}})
        owner.rows=[{"sha256":digest,"kind":"SOURCE_CANDIDATE","size_bytes":100}]
        owner.app.callbacks=replace(owner.app.callbacks, ingest=fail)
        self.check_hold(owner.app.run("S",now=NOW),"NATIVE_S03_INGEST_EXCEPTION_READBACK_REQUIRED")
        self.assertEqual(owner.calls,[])

    def test_p03_dispatch_exception_does_not_retry_uncertain_native_ack(self):
        owner=State()
        owner.app.callbacks=replace(owner.app.callbacks, dispatch=fail)
        receipt=owner.app.run("S",now=NOW)
        self.assertEqual(receipt["status"],"HOLD")
        self.assertEqual(receipt["enqueued_ids"],[])
        self.assertEqual(receipt["held"],[{"id":31,"reason":"NATIVE_QUEUE_EXCEPTION_READBACK_REQUIRED"}])
        self.assertEqual(owner.calls,[])
        self.assertFalse(receipt["release_accepted"])

    def test_normal_native_queue_still_works(self):
        owner=State()
        self.assertEqual(owner.app.run("S",now=NOW)["enqueued_ids"],[31,32])


if __name__=="__main__":
    unittest.main()
