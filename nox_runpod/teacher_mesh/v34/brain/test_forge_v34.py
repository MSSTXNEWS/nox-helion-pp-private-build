"""No fake GPU training success: admission and STOP gate tests."""
from __future__ import annotations
import hashlib
import unittest
from .forge_bridge_v34 import ExistingForgeBridge

SHA = 'a'*64

class TrustedHost:
    def __init__(self):
        self.owner = True; self.stop = False; self.submits = []; self.return_bad = False
        self.data = dict(vram_free_gb=20.0, ram_free_gb=25.0, disk_free_gb=120.0,
                         hotspot_c=49.0, hotspot_sensor_valid=True, hotspot_consecutive_high=0,
                         stop_active=False)

    def bridge(self):
        def submit(*args):
            self.submits.append(args)
            if self.return_bad:return {'state':'UNKNOWN'}
            return {'state':'ACCEPTED_BY_EXISTING_FORGE', 'job_id':'job-01'}
        return ExistingForgeBridge(owner_authorize=lambda *args:self.owner,
            native_stop=lambda:self.stop, native_telemetry=lambda:self.data,
            native_submit=submit)

    def run(self, **kwargs):
        return self.bridge().admit(tenant='tn',principal='me',chat_id='chat',
            owner_approval_receipt='native-signed-reference',
            student={'weights_sha256':SHA,'architecture_sha256':SHA,'tokenizer_sha256':SHA},
            dataset={'sha256':SHA,'source_disjoint':True,'license_and_privacy_reviewed':True},
            objective='association',**kwargs)

class ForgeChecks(unittest.TestCase):
    def test_native_submit_is_real_callback_and_not_optimizer_receipt(self):
        h=TrustedHost();r=h.run()
        self.assertEqual(r['state'],'NATIVE_FORGE_JOB_SUBMITTED_NOT_TRAINED')
        self.assertEqual(len(h.submits),1)
        self.assertFalse(r['student_weights_changed'])
        self.assertTrue(r['requires_native_optimizer_and_checkpoint_receipt'])

    def test_owner_not_approved_blocks(self):
        h=TrustedHost();h.owner=False;r=h.run()
        self.assertEqual(r['reason'],'SIGNED_NATIVE_OWNER_GRANT_REQUIRED');self.assertFalse(h.submits)

    def test_stop_holds_without_submitting(self):
        h=TrustedHost();h.stop=True
        self.assertEqual(h.run()['reason'],'NATIVE_STOP_ACTIVE_OR_UNAVAILABLE')
        self.assertFalse(h.submits)

    def test_sensor_missing_holds(self):
        h=TrustedHost();h.data['hotspot_sensor_valid']=False
        self.assertEqual(h.run()['reason'],'STOP_OR_HOTSPOT_SENSOR_NOT_VERIFIED')

    def test_hotspot_70_holds(self):
        h=TrustedHost();h.data['hotspot_c']=70.0
        self.assertEqual(h.run()['reason'],'HOTSPOT_AT_OR_ABOVE_70')

    def test_ram_low_holds(self):
        h=TrustedHost();h.data['ram_free_gb']=3
        self.assertEqual(h.run()['reason'],'RESOURCE_RESERVE_NOT_MET')

    def test_bad_nan_holds(self):
        h=TrustedHost();h.data['disk_free_gb']=float('nan')
        self.assertEqual(h.run()['reason'],'INVALID_GPU_OR_STORAGE_TELEMETRY')

    def test_only_existing_forge_receipt_counts(self):
        h=TrustedHost();h.return_bad=True
        self.assertEqual(h.run()['reason'],'UNVERIFIED_NATIVE_JOB_RECEIPT')

    def test_bad_objective_holds(self):
        h=TrustedHost();r=h.bridge().admit(tenant='tn',principal='me',chat_id='chat',
            owner_approval_receipt='x',student={},dataset={},objective='arbitrary_shell')
        self.assertEqual(r['reason'],'UNAPPROVED_OBJECTIVE')

if __name__ == '__main__':unittest.main()
