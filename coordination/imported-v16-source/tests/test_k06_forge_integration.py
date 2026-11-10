import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from nox_selfbuilder.background_forge import ExistingP04Background, ForgeJob, ForgeHold
from nox_selfbuilder.p04_forge_bridge import ExistingP04NativePorts, ForgeHold as PortHold

P04 = Path(__file__).resolve().parents[1] / 'Packages' / 'P04'

class ForgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / 'model'; self.model.mkdir()
        (self.model / 'config.json').write_text('{}')
        for name in ('lock.json', 'manifest.json', 'train.jsonl', 'holdout.jsonl', 'rights.exe'):
            (self.root / name).write_text('{}')
        self.events = []
        self.owner = ExistingP04Background(trusted_root=self.root, p04_dir=P04,
            owner_permit=lambda: True, owner_stop=lambda: False, owner_busy=lambda: False,
            event_sink=self.events.append)
        self.job = ForgeJob('run1', 'P04-1', self.model, self.root / 'lock.json', 'a'*40,
            self.root / 'manifest.json', self.root / 'rights.exe', self.root / 'train.jsonl',
            self.root / 'holdout.jsonl', self.root / 'result')

    def test_control_events_do_not_precreate_trainer_output(self):
        out = self.owner._output(self.job.output_dir)
        cmd, stop, pause = self.owner._job_command(self.job, out)
        self.assertFalse(out.exists())
        event_path = Path(cmd[cmd.index('--events-jsonl') + 1])
        self.assertFalse(event_path.is_relative_to(out))
        writer = self.owner.trainer.EventWriter(event_path, 'run1', 'P04-1')
        writer.emit('task.started', 'RUNNING', 'training', 'Actual worker start')
        self.assertFalse(out.exists(), 'EventWriter must not break trainer mkdir(exist_ok=False)')
        out.mkdir()  # original trainer can now claim its own fresh run directory

    def test_profile_limits_match_original(self):
        for profile, bound in (('ECO',20), ('BALANCED',40), ('INTENSIVE',80)):
            with self.assertRaises(ForgeHold):
                self.owner._job_command(replace(self.job, profile=profile, steps=bound+1), self.job.output_dir)

    def test_existing_output_is_never_overwritten(self):
        self.job.output_dir.mkdir()
        with self.assertRaises(ForgeHold): self.owner._output(self.job.output_dir)

    def test_symlink_parent_rejected(self):
        (self.root / 'alias').symlink_to(self.model, target_is_directory=True)
        with self.assertRaises(ValueError): self.owner._output(self.root / 'alias' / 'new')

    def test_48_hour_history_not_elapsed_claim(self):
        now = datetime.now(timezone.utc)
        self.assertFalse(self.owner.due(last_run_utc=now-timedelta(hours=47), now_utc=now))
        self.assertTrue(self.owner.due(last_run_utc=now-timedelta(hours=48), now_utc=now))

    def test_real_events_forward_once_and_preserve_not_verified(self):
        path = self.owner._control(self.job) / 'events.jsonl'
        writer = self.owner.trainer.EventWriter(path, 'run1', 'P04-1')
        writer.emit('training.step', 'RUNNING', 'training', 'Actual optimizer step', 1, 10)
        self.assertEqual(self.owner.relay_events(self.job), 1)
        self.assertEqual(self.owner.relay_events(self.job), 0)
        self.assertFalse(self.events[0]['evidence_verified'])

    def test_resume_requires_real_receipt_not_request_ack(self):
        self.job.output_dir.mkdir()
        with self.assertRaises((ForgeHold, ValueError, FileNotFoundError)):
            self.owner._job_command(self.job, self.job.output_dir, resume=True)

    def test_native_adapter_denies_ui_paths_and_uses_existing_scheduler(self):
        submissions = []
        ports = ExistingP04NativePorts(self.owner, job_resolver=lambda scope, id: self.job,
            last_run=lambda scope, job: None,
            native_submit=lambda scope, job, call: submissions.append(call) or {'status':'QUEUED'})
        with self.assertRaises(PortHold): ports.start(None, {'job_id':'approved', 'output_dir':'evil'})
        self.assertEqual(ports.start(None, {'job_id':'approved'})['status'], 'QUEUED')
        self.assertEqual(len(submissions), 1)
        self.assertFalse(self.job.output_dir.exists())

    def test_receipt_checkpoint_bytes_are_verified_and_mutation_rejected(self):
        t = self.owner.trainer
        out = self.job.output_dir; out.mkdir()
        adapter = out / 'adapter'; adapter.mkdir(); (adapter / 'weights').write_bytes(b'adapter')
        cp = out / 'checkpoints' / 'checkpoint-10'; cp.mkdir(parents=True)
        (cp / 'trainer_state.json').write_text('{"global_step":10}')
        for name in ('optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'adapter_model.bin'):
            (cp / name).write_bytes(b'preserved-state')
        self.job.model_lock.write_text('{"model_id":"local"}')
        receipt = {'schema': t.RECEIPT_SCHEMA, 'run_id':'run1', 'status':'PAUSED',
            'model':{'id':'local', 'revision':'a'*40, 'snapshot_sha256':t.sha256_tree(self.model)},
            'dataset':{'train_sha256':t.sha256_file(self.job.train_jsonl),
                       'holdout_sha256':t.sha256_file(self.job.holdout_jsonl)},
            'checkpoint':{'status':'HASHED','path':'checkpoints/checkpoint-10','step':10,
                          'tree_sha256':t.sha256_tree(cp)},
            'adapter_sha256':t.sha256_tree(adapter), 'training':{'global_step':10}}
        t.write_training_receipt(out, receipt)
        self.assertEqual(self.owner.verified_receipt(self.job)['status'], 'PAUSED')
        (cp / 'optimizer.pt').write_bytes(b'changed')
        with self.assertRaises(ForgeHold): self.owner.verified_receipt(self.job)

    def test_pause_cannot_cross_native_job_scope(self):
        controls = self.owner._control(self.job)
        self.owner._active = (controls / 'stop.marker', controls / 'pause.marker', 'run1', 'P04-1')
        with self.assertRaises(ForgeHold): self.owner.request_pause(replace(self.job, task_id='another'))
        self.assertFalse((controls / 'pause.marker').exists())
        self.assertEqual(self.owner.request_pause(self.job)['status'], 'PAUSE_REQUESTED')
        self.assertEqual(self.owner.request_stop()['status'], 'STOP_REQUESTED')
        self.assertEqual(self.owner.request_pause(self.job)['status'], 'STOP_REQUESTED')

    def test_unavailable_gpu_returns_truthful_hold(self):
        import os
        if os.name == 'nt': self.skipTest('requires absent Windows GPU fixture')
        result = self.owner.run_one(self.job, last_run_utc=None)
        self.assertEqual(result['reason'], 'GPU_TRAINING_HOLD')
        self.assertFalse(result['weights_updated'])
        self.assertFalse(self.job.output_dir.exists())

if __name__ == '__main__': unittest.main()
