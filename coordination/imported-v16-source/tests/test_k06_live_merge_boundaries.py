import unittest
from unittest.mock import patch
import test_k06_forge_integration as fixture
from nox_selfbuilder.p04_forge_bridge import ExistingP04NativePorts

class LiveMergeBoundaryTests(unittest.TestCase):
    setUp = fixture.ForgeIntegrationTests.setUp

    def test_merge_requires_separate_owner_consent_before_any_process(self):
        with patch('subprocess.Popen') as spawn:
            result = self.owner.merge_candidate(self.job, output_dir=self.root/'merged', owner_approve=lambda job,out:False)
        self.assertEqual(result['reason'], 'MERGE_OWNER_CONSENT_REQUIRED')
        spawn.assert_not_called()
        self.assertFalse((self.root/'merged').exists())

    def test_frozen_host_never_recursively_launches_itself_as_python(self):
        from nox_selfbuilder.background_forge import ExistingP04Background, ForgeHold
        import sys
        with patch.object(sys, 'frozen', True, create=True):
            with self.assertRaisesRegex(ForgeHold, 'P04_EXISTING_PYTHON_INTERPRETER_REQUIRED'):
                ExistingP04Background(trusted_root=self.root,p04_dir=self.p04 if hasattr(self,'p04') else fixture.P04,
                    owner_permit=lambda:True,owner_stop=lambda:False,owner_busy=lambda:False)
            with self.assertRaisesRegex(ForgeHold, 'P04_FROZEN_HOST_IS_NOT_TRAINER_INTERPRETER'):
                ExistingP04Background(trusted_root=self.root,p04_dir=fixture.P04,python_exe=sys.executable,
                    owner_permit=lambda:True,owner_stop=lambda:False,owner_busy=lambda:False)

    def test_global_stop_reaches_existing_merge_without_false_pause(self):
        self.owner._merge_active = True
        self.assertEqual(self.owner.request_pause()['status'], 'HOLD')
        self.assertEqual(self.owner.request_stop()['status'], 'STOP_REQUESTED')
        self.assertTrue(self.owner._merge_stop)

    def test_checkpoints_poll_real_events_before_terminal_receipt(self):
        event_path = self.owner._control(self.job)/'events.jsonl'
        writer = self.owner.trainer.EventWriter(event_path, 'run1', 'P04-1')
        writer.emit('training.step','RUNNING','training','Actual optimizer callback',1,10)
        ports = ExistingP04NativePorts(self.owner,
            job_resolver=lambda scope, id:self.job, last_run=lambda scope,job:None,
            native_submit=lambda *args:None)
        result = ports.checkpoints(None, {'job_id':'run1'})
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(result['reason'],'AWAITING_VERIFIED_CHECKPOINT')
        self.assertEqual(result['events'][0]['numerator'],1)
        self.assertFalse(result['events'][0]['evidence_verified'])
        self.assertIsNone(result['checkpoint'])

if __name__=='__main__':unittest.main()
