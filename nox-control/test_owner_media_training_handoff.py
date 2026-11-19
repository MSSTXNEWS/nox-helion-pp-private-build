"""Owned media yield, persistent retry and sealed continuation semantics."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import owner_media_training_handoff as handoff
import owner_plan_native_actions as actions

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for module in (handoff, actions):
            item = patch.object(module, 'ROOT', self.root); item.start(); self.addCleanup(item.stop)
        actions._HASH_CACHE.clear()
        self.jid = 'f' * 32
        self.started = False
        self.starts = []
        self.gpu_free = 32000
        self.main_config = self.root / 'config/owner_media_runtime.json'
        handoff.atomic(self.main_config, {'enabled': True, 'engine_service': 'nox-media-comfyui'})
        self.media_before = self.main_config.read_bytes()
        for name in ('owner_media_runtime.py', 'owner_media_install.py'):
            target = self.root / 'scripts' / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / name, target)
        self.context = {'request': '6900000000', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        self.pointer = {'schema': 'NOX_OWNER_TRAINING_ADMISSION_V1', 'max_steps': 1000,
                        'resume': True, 'wrapper_request': self.context['request']}
        self.lineage = 'c' * 64
        self.wrapper = self.root / 'scripts/run_train_volta_t866u.sh'
        self.wrapper.write_text('#!/bin/bash\nfixed reviewed --max-steps 1000 --planned-steps 1000 --resume\n')
        (self.root / 'state').mkdir(exist_ok=True)
        (self.root / 'state/train_cpu_max.env').write_text('TRAIN_CPU_MAX=64GiB\n')
        (self.root / 'state/train_wants_gpu1').write_text('reservation retained')
        self.output = self.root / 'lora/qlora_t866u/runs_owner_hybrid'
        checkpoint = self.output / 'checkpoint-8'; checkpoint.mkdir(parents=True)
        for name in handoff.CHECKPOINT_NAMES:
            (checkpoint / name).write_bytes(('checkpoint-' + name).encode())
        (checkpoint / 'trainer_state.json').write_text(json.dumps({'global_step': 8}))
        self.terminal = {'schema': actions.TRAIN_SCHEMA, 'native_sha256': actions.NATIVE_SHA,
            'state': 'CHECKPOINTED_OWNER_STOP', 'global_step': 8, 'start_step': 5,
            'successful_optimizer_steps': 2, 'skipped_optimizer_steps': 1, 'loss': 1.2,
            'adapter_delta_verified': True, 'lineage_sha256': self.lineage,
            'before_tensor_sha256': '1' * 64, 'after_tensor_sha256': '2' * 64,
            'checkpoint': {'path': str(checkpoint), 'global_step': 8,
                'files_sha256': {name: sha((checkpoint / name).read_bytes()) for name in handoff.CHECKPOINT_NAMES}}}
        self.result_path = self.output / 'owner_last_result.json'
        handoff.atomic(self.result_path, self.terminal)
        self.pause_text = 'NOX_MEDIA_CHECKPOINT_YIELD ' + self.jid + '\n'
        self.hold_text = 'OWNER_HYBRID_BOUNDED_COMPLETE request=' + self.context['request'] + '\n'
        self.pause = self.root / 'state/TRAIN_PAUSE_REQUEST.flag'; self.pause.write_text(self.pause_text)
        self.hold = self.root / 'state/TRAIN_HOLD.flag'; self.hold.write_text(self.hold_text)
        self.yielded = {'active': True, 'resume': True, 'job_id': self.jid,
            'requested_at': time.time() - 10, 'pause_token': self.pause_text,
            'wrapper_sha256': sha(self.wrapper.read_bytes()), 'hold_sha256': sha(self.hold_text.encode()),
            'trainer_before': {'state': 'RUNNING', 'pid': 333, 'rc': 0},
            'checkpoint': {'step': 8, 'receipt_sha256': sha(self.result_path.read_bytes()), 'checkpoint': str(checkpoint)}}
        handoff.atomic(self.root / 'state/media/training_yield.json', self.yielded)
        self.job = {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': self.jid,
                    'state': 'COMPLETED', 'generation_verified': True}
        handoff.atomic(self.root / 'state/media/jobs' / (self.jid + '.json'), self.job)
        self.cleanup_calls = []
        self.runtime = types.SimpleNamespace(__file__=str(self.root / 'scripts/owner_media_runtime.py'),
            resume_training=lambda *args: self.cleanup_calls.append(args) or 'TRAINING_PREVIOUSLY_HELD',
            gpu1=lambda: {'free_mib': self.gpu_free}, queue_ids=lambda: {'queue_running': [], 'queue_pending': []})
        self.mentor = types.SimpleNamespace(stop_active=lambda: False, verify_success=lambda *args: {'delegated': True})
        self.ns = {'STATE': self.root / 'state/dispatcher/state.json', 'WORKERS': 6,
            'owner_mentor': self.mentor, 'HANDLERS': {}, 'ingest_owner_orders': lambda state: None,
            '_nox_owner_task_admitted': lambda task: False, '_owner_media_bound': True, '_owner_plans_bound': True}
        self.process = {'pid': 444, 'ppid': 445, 'pgrp': 445, 'state': 'S', 'cuda': '1',
                        'service': handoff.SERVICE, 'starttime': '0'}
        self.helper = types.SimpleNamespace(HEAVY_SERVICES={'old-heavy-service': 'fixed.py'},
            service_state=self.service, process_table=lambda: {}, health=lambda: {'8081': 200}, command=self.command)
        self.disk_guard = types.SimpleNamespace(admission=lambda context: (self.pointer, {'lineage': True}, {'first': 5}),
            checkpoint_budget=lambda *args: {'required_free_bytes': 5 * 1024 ** 3})
        self.native = types.SimpleNamespace(ns=self.ns, admission=self.context,
            helper=self.helper, disk_guard=self.disk_guard,
            training_context=lambda: (copy.deepcopy(self.pointer), self.lineage), trainer_process=self.trainer)
        self.bound = handoff.Handback(self.ns, self.runtime, self.native, actions.checkpoint_proof)
        self.config = {'schema': handoff.CONFIG_SCHEMA, 'enabled': True, 'resume_training_after_media': True,
            'source_sha256': self.bound.source_pin, 'runtime_sha256': handoff.MEDIA_SHA,
            'installer_sha256': handoff.INSTALLER_SHA, 'media_config_sha256': sha(self.media_before),
            'initial_admission': self.context}
        handoff.atomic(self.root / handoff.CONFIG, self.config)
        original_read_text = Path.read_text
        def read_text(path, *args, **kwargs):
            if str(path) == '/sys/fs/cgroup/memory.max': return str(181 * 1024 ** 3)
            if str(path) == '/sys/fs/cgroup/memory.current': return str(50 * 1024 ** 3)
            return original_read_text(path, *args, **kwargs)
        item = patch.object(Path, 'read_text', read_text); item.start(); self.addCleanup(item.stop)
        item = patch.object(handoff.os, 'statvfs', return_value=types.SimpleNamespace(f_bavail=15 * 1024 ** 3, f_frsize=1))
        item.start(); self.addCleanup(item.stop)

    def service(self, name):
        if name == handoff.SERVICE and self.started:
            return {'state': 'RUNNING', 'pid': self.process['ppid'], 'rc': 0}
        return {'state': 'STOPPED', 'pid': None, 'rc': 0}

    def command(self, args, timeout):
        self.starts.append((args, timeout)); self.started = True
        self.process['starttime'] = str(int(time.clock_gettime(time.CLOCK_BOOTTIME) * os.sysconf('SC_CLK_TCK')))
        return 0, 'private command output is not exposed'

    def trainer(self):
        if not self.started:
            raise actions.ActionHold('WAIT_SINGLE_ADMITTED_TRAINER_PROCESS')
        return copy.deepcopy(self.process)

    def task(self):
        state = {'tasks': {}}
        self.bound.ingest(state)
        task = state['tasks']['owner.media.resume.' + self.jid]
        task.update(status='running', claimed_by='nox-agent-01', owner_claim_epoch=time.time(),
                    owner_claim={'worker': 'nox-agent-01', 'pid': os.getpid(), 'nonce': 'd' * 24, 'at': '2026-11-16T00:00:00Z'})
        handoff.atomic(self.ns['STATE'], state)
        return task

    def assert_flags_retained(self):
        self.assertEqual(self.pause.read_text(), self.pause_text)
        self.assertEqual(self.hold.read_text(), self.hold_text)
        self.assertFalse(self.starts)


class HandoffTests(Fixture):
    def test_callback_creates_durable_request_without_starting_and_preserves_main_config(self):
        self.assertEqual(self.bound.callback(self.job, {'resume_training_after_media': True}, self.yielded), 'TRAINING_RESUME_QUEUED')
        self.assertEqual(self.main_config.read_bytes(), self.media_before)
        self.assert_flags_retained()
        self.assertEqual(handoff.document(self.bound.directory(self.jid) / 'request.json')['stage'], 'QUEUED')
        self.assertFalse(self.cleanup_calls)

    def test_disabled_config_never_delegates_to_old_active_auto_start(self):
        self.config['enabled'] = False
        handoff.atomic(self.root / handoff.CONFIG, self.config)
        result = self.bound.callback(self.job, {'resume_training_after_media': True}, self.yielded)
        self.assertEqual(result, 'WAIT_MEDIA_HANDBACK_NOT_ENABLED')
        self.assert_flags_retained(); self.assertFalse(self.cleanup_calls)
        self.assertTrue(self.job['generation_verified'])

    def test_previously_held_trainer_delegates_only_inactive_cleanup(self):
        self.assertEqual(self.bound.callback(self.job, {}, {'active': False, 'resume': False}), 'TRAINING_PREVIOUSLY_HELD')
        self.assertEqual(len(self.cleanup_calls), 1); self.assertFalse(self.starts)

    def test_cancelled_last_job_is_reconciled_once_without_replaying_previous_task(self):
        self.job.update(state='CANCELLED', generation_verified=False)
        handoff.atomic(self.root / 'state/media/jobs' / (self.jid + '.json'), self.job)
        state = {'tasks': {}}
        self.bound.ingest(state); self.bound.ingest(state)
        self.assertEqual(len(state['tasks']), 1)
        task = next(iter(state['tasks'].values())); task['status'] = 'blocked'
        self.bound.ingest(state)
        self.assertEqual(task['status'], 'blocked')

    def test_active_other_media_waits_then_retries_existing_handback(self):
        task = self.task()
        other = 'a' * 32
        handoff.atomic(self.root / 'state/media/jobs' / (other + '.json'),
                       {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': other, 'state': 'QUEUED'})
        ok, result = self.bound.run(task)
        self.assertEqual((ok, result['state']), ('wait', 'WAIT_MEDIA_QUEUE_DRAIN'))
        self.assert_flags_retained()
        handoff.atomic(self.root / 'state/media/jobs' / (other + '.json'),
                       {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': other, 'state': 'CANCELLED'})
        self.assertIs(self.bound.run(task)[0], True)
        self.assertEqual(len(self.starts), 1)

    def test_only_exact_typed_task_is_admitted_and_other_handlers_delegate(self):
        task = self.task()
        self.assertTrue(self.bound.admitted(task))
        for mutation in ({'class': 'owner_order'}, {'source': 'chat'}, {'locks': []},
                         {'params': {'job_id': self.jid, 'command': 'arbitrary'}}, {'id': 'spoof'}):
            with self.subTest(mutation=mutation):
                self.assertFalse(self.bound.admitted({**task, **mutation}))
        self.assertFalse(self.bound.admitted({'handler': 'start_qlora'}))

    def test_stop_and_held_maintenance_never_clear_flags(self):
        task = self.task()
        (self.root / 'STOP').write_text('owner requested stop')
        self.assertEqual(self.bound.run(task)[0], 'wait'); self.assert_flags_retained()
        (self.root / 'STOP').unlink()
        with handoff.exclusive(self.root / 'state/owner_maintenance.lock', 'WAIT_TEST'):
            self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_OWNER_MAINTENANCE')
        self.assert_flags_retained()

    def test_sealed_initial1000_context_and_persisted_claim_required(self):
        task = self.task()
        self.native.training_context = lambda: handoff.hold('WAIT_INITIAL_TRAINING_ADMISSION')
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_INITIAL_TRAINING_ADMISSION')
        self.assert_flags_retained()
        self.native.training_context = lambda: (copy.deepcopy(self.pointer), self.lineage)
        changed = copy.deepcopy(task); changed['owner_claim']['nonce'] = 'e' * 24
        self.assertEqual(self.bound.run(changed)[1]['state'], 'HOLD_MEDIA_HANDBACK_PERSISTED_CLAIM')
        self.assert_flags_retained()

    def test_foreign_pause_or_completion_hold_and_changed_wrapper_are_preserved(self):
        task = self.task()
        self.pause.write_text('OWNER_DISK_RESERVE_PAUSE foreign\n')
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_UNOWNED_TRAINING_HOLD_OR_PAUSE')
        self.assertEqual(self.pause.read_text(), 'OWNER_DISK_RESERVE_PAUSE foreign\n'); self.assertFalse(self.starts)
        self.pause.write_text(self.pause_text); self.hold.write_text('OWNER_HYBRID_FAILED request=other\n')
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_UNOWNED_TRAINING_HOLD_OR_PAUSE')
        self.assertEqual(self.hold.read_text(), 'OWNER_HYBRID_FAILED request=other\n')
        self.hold.write_text(self.hold_text); self.wrapper.write_text('changed wrapper')
        self.assertEqual(self.bound.run(task)[1]['state'], 'HOLD_MEDIA_HANDBACK_WRAPPER_CHANGED')

    def test_full_optimizer_hash_required_and_global_steps_are_not_sufficient(self):
        task = self.task()
        optimizer = self.output / 'checkpoint-8/optimizer.pt'; original = optimizer.read_bytes()
        optimizer.write_bytes(b'tampered optimizer')
        self.assertEqual(self.bound.run(task)[1]['state'], 'HOLD_NATIVE_ACTION_ARTIFACT_HASH')
        self.assert_flags_retained(); optimizer.write_bytes(original)
        self.terminal['successful_optimizer_steps'] = 0; self.terminal['skipped_optimizer_steps'] = 3
        handoff.atomic(self.result_path, self.terminal)
        self.yielded['checkpoint']['receipt_sha256'] = sha(self.result_path.read_bytes())
        handoff.atomic(self.root / 'state/media/training_yield.json', self.yielded)
        self.assertEqual(self.bound.run(task)[1]['state'], 'HOLD_NATIVE_CHECKPOINT_OPTIMIZER_PROOF')
        self.assert_flags_retained()

    def test_gpu_ram_disk_and_engine_queue_waits_preserve_owned_pause(self):
        task = self.task()
        self.gpu_free = 29000
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_TRAINING_GPU1_HEADROOM'); self.assert_flags_retained()
        self.gpu_free = 32000
        self.disk_guard.checkpoint_budget = lambda *args: {'required_free_bytes': 16 * 1024 ** 3}
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_TRAINING_CHECKPOINT_DISK_RESERVE'); self.assert_flags_retained()
        self.disk_guard.checkpoint_budget = lambda *args: {'required_free_bytes': 5 * 1024 ** 3}
        (self.root / 'state/train_cpu_max.env').write_text('TRAIN_CPU_MAX=128GiB\n')
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_TRAINING_RAM_HEADROOM'); self.assert_flags_retained()
        (self.root / 'state/train_cpu_max.env').write_text('TRAIN_CPU_MAX=64GiB\n')
        self.runtime.queue_ids = lambda: {'queue_running': [], 'queue_pending': ['foreign']}
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_MEDIA_ENGINE_QUEUE_DRAIN'); self.assert_flags_retained()

    def test_success_restarts_exact_wrapper_once_and_proof_never_claims_new_learning(self):
        task = self.task()
        ok, evidence = self.bound.run(task)
        self.assertIs(ok, True)
        self.assertEqual(self.starts, [(['supervisorctl', 'start', handoff.SERVICE], 35)])
        self.assertFalse(self.pause.exists()); self.assertFalse(self.hold.exists())
        self.assertEqual(self.main_config.read_bytes(), self.media_before)
        yielded = handoff.document(self.root / 'state/media/training_yield.json')
        self.assertFalse(yielded['active']); self.assertFalse(yielded['resume'])
        receipt = handoff.document(evidence['receipt_path'])
        self.assertFalse(receipt['optimizer_progress_since_resume_verified'])
        self.assertFalse(receipt['weights_promoted'])
        self.assertEqual(receipt['baseline_step'], 8)
        task['status'] = 'done'
        proof = self.bound.verify(task, evidence)
        self.assertEqual(proof['kind'], 'bounded_native_component_check')
        self.assertEqual(proof['scope'], handoff.SCOPE)
        self.assertIsNone(self.bound.verify(task, {**evidence, 'receipt_sha256': '0' * 64}))
        receipt['claim']['nonce'] = '0' * 24
        handoff.atomic(evidence['receipt_path'], receipt)
        self.assertIsNone(self.bound.verify(task, evidence))

    def test_source_or_main_configuration_change_does_not_start_training(self):
        task = self.task()
        handoff.atomic(self.main_config, {'enabled': True, 'resume_training_after_media': True})
        self.assertFalse(self.bound.admitted(task))
        self.assert_flags_retained()

    def test_start_failure_restores_own_flags_without_overwriting_new_foreign_hold(self):
        task = self.task()
        def failed(args, timeout):
            self.starts.append((args, timeout))
            self.hold.write_text('OWNER_NEW_HOLD preserved\n')
            return 1, 'private failure'
        self.helper.command = failed
        ok, result = self.bound.run(task)
        self.assertIs(ok, False)
        self.assertEqual(result['state'], 'HOLD_MEDIA_HANDBACK_START_NOT_VERIFIED')
        self.assertEqual(self.pause.read_text(), self.pause_text)
        self.assertEqual(self.hold.read_text(), 'OWNER_NEW_HOLD preserved\n')
        self.assertEqual(handoff.document(self.bound.directory(self.jid) / 'request.json')['stage'], 'START_UNVERIFIED')
        self.assertFalse(self.bound.admitted(task))

    def test_partial_owned_flag_archive_recovers_only_after_all_admission_gates(self):
        task = self.task()
        directory = self.bound.directory(self.jid)
        record = handoff.document(directory / 'request.json')
        record.update(stage='START_INTENT', start_command_issued=False)
        handoff.atomic(directory / 'request.json', record)
        os.link(self.pause, directory / 'released-TRAIN_PAUSE_REQUEST.flag')
        self.pause.unlink()
        self.gpu_free = 28000
        self.assertEqual(self.bound.run(task)[1]['state'], 'WAIT_TRAINING_GPU1_HEADROOM')
        self.assertFalse(self.starts)
        self.assertEqual(self.hold.read_text(), self.hold_text)
        self.gpu_free = 32000
        self.assertIs(self.bound.run(task)[0], True)
        self.assertEqual(len(self.starts), 1)

    def test_interrupted_final_receipt_attaches_existing_process_without_second_start(self):
        task = self.task()
        with patch.object(self.bound, 'receipt', side_effect=OSError('private disk exception')):
            ok, evidence = self.bound.run(task)
        self.assertIs(ok, False)
        self.assertNotIn('private disk exception', json.dumps(evidence))
        self.assertEqual(len(self.starts), 1)
        self.assertFalse(handoff.document(self.root / 'state/media/training_yield.json')['active'])
        # A separately persisted reconciled claim can finish receipt publication;
        # ingest itself never resets a blocked or in-flight task.
        task['owner_claim']['nonce'] = 'e' * 24
        task['owner_claim_epoch'] = time.time()
        handoff.atomic(self.ns['STATE'], {'tasks': {task['id']: task}})
        self.assertIs(self.bound.run(task)[0], True)
        self.assertEqual(len(self.starts), 1)

    def test_rpc_timeout_with_real_owned_running_process_is_verified_by_identity(self):
        task = self.task()
        original = self.helper.command
        def command(args, timeout):
            original(args, timeout)
            return 124, 'transport timeout'
        self.helper.command = command
        self.assertIs(self.bound.run(task)[0], True)
        self.assertEqual(len(self.starts), 1)

    def test_missing_original_job_cannot_turn_a_stale_yield_into_a_restart(self):
        task = self.task()
        (self.root / 'state/media/jobs' / (self.jid + '.json')).unlink()
        self.assertEqual(self.bound.run(task)[1]['state'], 'HOLD_MEDIA_HANDBACK_ORIGINAL_JOB_MISSING')
        self.assert_flags_retained()

    def test_fifo_and_duplicate_json_keys_are_rejected_without_blocking(self):
        path = self.root / 'fifo'; os.mkfifo(path)
        with self.assertRaisesRegex(handoff.HandoffHold, 'FILE_SCOPE'):
            handoff.read(path)
        path = self.root / 'duplicate.json'; path.write_text('{"state":1,"state":2}')
        with self.assertRaisesRegex(handoff.HandoffHold, 'DUPLICATE_KEY'):
            handoff.document(path)

    def test_binder_preserves_runtime_file_and_native_media_configuration(self):
        before = Path(self.runtime.__file__).read_bytes()
        handoff.bind_dispatcher(self.ns, self.runtime, self.native, actions.checkpoint_proof)
        self.assertTrue(self.ns['_owner_media_training_handoff_bound'])
        self.assertIn(handoff.TASK_HANDLER, self.ns['HANDLERS'])
        self.assertEqual(Path(self.runtime.__file__).read_bytes(), before)
        self.assertEqual(self.main_config.read_bytes(), self.media_before)
        self.assertEqual(self.mentor.verify_success({'handler': 'unrelated'}), {'delegated': True})


if __name__ == '__main__':
    unittest.main()
