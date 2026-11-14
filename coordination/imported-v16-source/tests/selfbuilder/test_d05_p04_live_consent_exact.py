"""D05 source regression: existing P04 cannot treat unknown native owner callbacks as consent.

This tests the original Python handler with no GPU subprocess; Windows installed
training, SI D/ACL and same-Setup E07 remain independent physical requirements.
"""
import threading
import unittest
from pathlib import Path
from src.nox_selfbuilder.background_forge import ExistingP04Background

class D05NativeOwnerGrantTests(unittest.TestCase):
    @staticmethod
    def fresh(stop=False, permit=True, busy=False):
        p=object.__new__(ExistingP04Background)
        p.stop=lambda: stop
        p.permit=lambda: permit
        p.busy=lambda: busy
        p._gate=threading.Lock()
        p._control_lock=threading.Lock()
        p._unreaped_worker=None
        return p

    def test_exact_native_owner_grants(self):
        cases=(
            (False,True,False,True,True),
            (True,True,False,True,False),
            (None,True,False,True,False),
            (0,True,False,True,False),
            ('',True,False,True,False),
            (False,None,False,True,False),
            (False,1,False,True,False),
            (False,False,False,True,False),
            (False,True,None,True,False),
            (False,True,True,True,False),
            (False,True,None,False,True),
            (False,True,True,False,True),
        )
        for stop,permit,busy,idle,expected in cases:
            with self.subTest(stop=stop,permit=permit,busy=busy,idle=idle):
                owner=self.fresh(stop,permit,busy)
                self.assertIs(owner._owner_training_grant(require_idle=idle),expected)

    def test_run_refuses_unknown_stop_before_preflight(self):
        owner=self.fresh(stop=None)
        owner.preflight=lambda job: self.fail('GPU diagnostic must not run')
        receipt=owner._run(object(),.01,10,False,True)
        self.assertEqual(receipt['status'],'HOLD')
        self.assertEqual(receipt['reason'],'NO_OWNER_IDLE_CONSENT_OR_STOP')

    def test_run_refuses_unknown_idle_before_preflight(self):
        owner=self.fresh(busy=None)
        owner.preflight=lambda job: self.fail('GPU diagnostic must not run')
        receipt=owner._run(object(),.01,10,False,True)
        self.assertEqual(receipt['status'],'HOLD')

    def test_merge_refuses_nonliteral_native_consent_without_filesystem_access(self):
        owner=self.fresh(permit=1)
        owner.verified_receipt=lambda job: self.fail('merge must not read trainer')
        receipt=owner.merge_candidate(object(),output_dir=Path('unused'),owner_approve=lambda *_: True)
        self.assertEqual(receipt['status'],'HOLD')
        self.assertEqual(receipt['reason'],'MERGE_OWNER_REVOKED')

if __name__=='__main__':
    unittest.main()
