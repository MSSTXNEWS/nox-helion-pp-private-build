"""Finite recovery chain: guard errors request only an identity-bound yield."""
import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('recovery_chain_test',HERE/'owner_training_recovery_chain.py')
chain=importlib.util.module_from_spec(spec);spec.loader.exec_module(chain)


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)
        p=patch.object(chain,'STATE',self.state);p.start();self.addCleanup(p.stop)
        self.context={'request':'123456','source_sha':'a'*40,'receipt_sha256':'b'*64}
        self.process={'pid':44,'starttime':900}
        self.guard=types.SimpleNamespace(plain=lambda path:Path(path),admission=Mock(return_value=({}, {}, {})),
            trainer_process=Mock(return_value=self.process))

    def test_all_bundle_pins_are_current_reviewed_files(self):
        for name,pin in [('owner_training_recovery_entry.py',chain.RECOVERY_SHA),
                         ('owner_training_disk_guard_entry.py',chain.GUARD_INSTALL_SHA),
                         ('owner_training_disk_guard.py',chain.GUARD_SHA)]:
            self.assertEqual(chain.digest((HERE/name).read_bytes()),pin)

    def test_guard_failure_creates_only_checkpoint_pause_after_exact_admission(self):
        result=chain.pause_unprotected(self.guard,self.context)
        self.guard.admission.assert_called_once_with(self.context)
        self.assertEqual(self.guard.trainer_process.call_count,2)
        self.assertTrue(result['pause_created']);self.assertFalse(result['checkpoint_completion_verified'])
        expected=b'OWNER_DISK_GUARD_UNAVAILABLE request=123456 source='+b'a'*40+b'\n'
        self.assertEqual((self.state/'TRAIN_PAUSE_REQUEST.flag').read_bytes(),expected)
        self.assertEqual((self.state/'TRAIN_PAUSE_REQUEST.flag').stat().st_mode&0o777,0o600)
        self.assertFalse((self.state/'TRAIN_HOLD.flag').exists())

    def test_new_owner_pause_is_never_overwritten(self):
        path=self.state/'TRAIN_PAUSE_REQUEST.flag';path.write_bytes(b'owner new request')
        result=chain.pause_unprotected(self.guard,self.context)
        self.assertFalse(result['pause_created']);self.assertEqual(path.read_bytes(),b'owner new request')

    def test_no_pause_for_wrong_admission_or_changed_process(self):
        self.guard.admission.side_effect=RuntimeError('HOLD_WRONG_ADMISSION')
        with self.assertRaisesRegex(RuntimeError,'WRONG_ADMISSION'):chain.pause_unprotected(self.guard,self.context)
        self.assertFalse((self.state/'TRAIN_PAUSE_REQUEST.flag').exists())
        self.guard.admission.side_effect=None
        self.guard.trainer_process.side_effect=[self.process,{**self.process,'starttime':901}]
        with self.assertRaisesRegex(RuntimeError,'PROCESS_CHANGED'):chain.pause_unprotected(self.guard,self.context)
        self.assertFalse((self.state/'TRAIN_PAUSE_REQUEST.flag').exists())

    def test_terminal_trainer_is_reported_without_new_flag(self):
        self.guard.trainer_process.return_value=None
        result=chain.pause_unprotected(self.guard,self.context)
        self.assertEqual(result['state'],'ADMITTED_TRAINER_NOT_RUNNING')
        self.assertFalse((self.state/'TRAIN_PAUSE_REQUEST.flag').exists())

    def test_actual_guard_readback_required_and_failure_is_partial(self):
        installer=types.SimpleNamespace(main=Mock(return_value=0))
        recovery=types.SimpleNamespace(document=lambda path:{'state':'INSTALLED_AWAITING_NATIVE_POLL'})
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123456'}):
            stage,ok=chain.install_guard_or_pause(recovery,installer,self.guard,self.context)
        self.assertFalse(ok);self.assertEqual(stage['state'],'GUARD_UNVERIFIED')
        self.assertTrue(stage['checkpoint_pause']['pause_created'])

    def test_verified_poll_does_not_request_pause(self):
        row={'state':'EXISTING_PRIORITY_DISK_GUARD_VERIFIED','initial_admission':self.context,
            'guard_source_sha256':chain.GUARD_SHA,'scheduler_after_sha256':'d'*64,
            'native_observation':{'state':'CHECKPOINT_DISK_HEADROOM_ADMITTED'}}
        installer=types.SimpleNamespace(main=lambda context:0);recovery=types.SimpleNamespace(document=lambda path:row)
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123456'}):
            stage,ok=chain.install_guard_or_pause(recovery,installer,self.guard,self.context)
        self.assertTrue(ok);self.assertEqual(stage['state'],'NATIVE_DISK_GUARD_VERIFIED')
        self.guard.admission.assert_not_called();self.assertFalse((self.state/'TRAIN_PAUSE_REQUEST.flag').exists())


if __name__=='__main__':unittest.main()
