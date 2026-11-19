"""No native calls: shared lease, source closure and live guard compatibility."""
import base64
from contextlib import nullcontext
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('current_qwen_capacity_test', HERE / 'owner_qwen_current_capacity_batch.py')
batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)


def bundle():
    return {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in batch.PINS}


def case(n):
    return {'concurrency': n, 'samples': 6, 'completed_samples': 6, 'native_streams_completed': 6,
            'passed': 5, 'state': 'QUALITY_FAILED', 'hold_reason': None,
            'p95_ttft_ms': 400., 'p95_total_ms': 900., 'useful_tasks_per_sec': float(n)}


def snapshot():
    return {'chat_identity': {'pid': 7637, 'start_ticks': 149189867, 'model_slots': 6},
            'training_service': {'state': 'RUNNING', 'pid': 123}, 'resources': {}, 'model_slots': 6}


class CapacityBatchTests(unittest.TestCase):
    def prepared(self):
        with patch.object(batch, 'BUNDLE', bundle()):
            return batch.prepared()

    def fake_guard(self, *, sampled=None, inhibited=False, checkpoint=None):
        cfg = {'policy': {'state_max_age_seconds': 30}}
        cp = {'manifest_sha256': 'a' * 64}
        row = {'sampled_at': time.time() if sampled is None else sampled,
               'state': 'INHIBITED' if inhibited else 'MONITORING',
               'policy_state': {'inhibit': inhibited}, 'checkpoint': cp}
        return types.SimpleNamespace(_IO_DEADLINE=threading.local(),
            checked_config=Mock(return_value=(cfg, 'b' * 64)), context_evidence=Mock(return_value={}),
            bindings=Mock(return_value={'fixture': 'binding'}), previous_state=Mock(return_value=(row, 'c' * 64)),
            checkpoint_metadata=Mock(return_value=cp if checkpoint is None else checkpoint))

    def test_exact_closure_loads_definitions_without_native_io(self):
        with patch('os.open', side_effect=AssertionError('native IO')), patch('subprocess.run', side_effect=AssertionError('service IO')):
            training, media, capacity = self.prepared()
        self.assertEqual(capacity.REQUESTED, (1, 3, 6))
        self.assertEqual(media.RUNTIME_SHA, batch.RUNTIME_SHA)
        self.assertEqual(training.PINS['owner_qwen_training_guard.py'], batch.GUARD_SHA)
        bad = bundle(); bad['owner_qwen_current_observe.py'] = base64.b64encode(b'pass').decode()
        with patch.object(batch, 'BUNDLE', bad), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            batch.prepared()

    def test_shared_lease_permits_guard_shared_and_blocks_owner_exclusive(self):
        with tempfile.TemporaryDirectory() as root:
            core = types.SimpleNamespace(STATE=Path(root), checked=lambda p: p)
            path = Path(root) / 'owner_maintenance.lock'
            with self.assertRaises(FileNotFoundError), batch.shared_existing_lease(core):
                pass
            self.assertFalse(path.exists())
            path.write_bytes(b''); path.chmod(0o600)
            before = path.stat()
            with batch.shared_existing_lease(core):
                guard_fd, owner_fd = os.open(path, os.O_RDONLY), os.open(path, os.O_RDONLY)
                try:
                    fcntl.flock(guard_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(guard_fd); os.close(owner_fd)
            self.assertEqual((before.st_size, before.st_mtime_ns), (path.stat().st_size, path.stat().st_mtime_ns))
            fd = os.open(path, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, 'OWNER_MAINTENANCE'), batch.shared_existing_lease(core):
                    pass
            finally:
                os.close(fd)

    def test_guard_reader_is_fresh_context_bound_and_never_ticks(self):
        guard = self.fake_guard()
        expected, row = batch.fresh_guard(guard, 'RUNNING')
        self.assertEqual(expected, {'fixture': 'binding'})
        self.assertFalse(row['guard_tick_called'])
        guard.checked_config.assert_called_once_with(batch.WINDOW_CONTEXT, batch.GUARD_SHA)
        with self.assertRaisesRegex(RuntimeError, 'GUARD_STALE'):
            batch.fresh_guard(self.fake_guard(sampled=time.time() - 31), 'RUNNING')
        with self.assertRaisesRegex(RuntimeError, 'GUARD_CHECKPOINT_PENDING'):
            batch.fresh_guard(self.fake_guard(checkpoint={'manifest_sha256': 'd' * 64}), 'RUNNING')
        with self.assertRaisesRegex(RuntimeError, 'GUARD_INHIBITED'):
            batch.fresh_guard(self.fake_guard(inhibited=True), 'RUNNING')
        _, paused = batch.fresh_guard(self.fake_guard(inhibited=True), 'STOPPED')
        self.assertTrue(paused['inhibit'])

    def test_each_136_gate_preserves_quality_failure_and_checks_guard(self):
        _, _, capacity = self.prepared()
        core, probe = capacity.helpers()
        core.services = Mock(return_value={'nox-media-comfyui': {'state': 'RUNNING'}})
        core.http_json = Mock(return_value={'data': [{'id': str(core.ROOT / 'models/current.gguf')}]})
        probe.infer = Mock(return_value={'stream_done': True, 'finish_reason': 'stop', 'ttft_ms': 1.})
        probe.burst = Mock(side_effect=[case(n) for n in (1, 3, 6)])
        capacity.helpers = Mock(return_value=(core, probe))
        capacity.gate = Mock(side_effect=lambda *a, **k: snapshot())
        observed = batch.configure_private_capacity(capacity, self.fake_guard())
        result = {'cases': []}
        with patch.object(batch, 'dispatcher_scope', return_value={'sha256': batch.DISPATCHER_SHA}), patch.object(batch, 'fresh_guard', return_value=({'scope': 'known'}, {'state': 'MONITORING'})) as checked:
            core, probe = capacity.helpers()
            capacity.run_series(core, probe, result)
        self.assertEqual([call.args[1] for call in probe.burst.call_args_list], [1, 3, 6])
        self.assertEqual(checked.call_count, 6)
        self.assertIs(capacity.existing_lease, batch.shared_existing_lease)
        self.assertTrue(result['measured']['sweep_complete'])
        self.assertFalse(result['measured']['all_fixture_quality_passed'])
        self.assertIsNone(result['measured']['recommended_tested_total_concurrency'])
        self.assertFalse(result['measured']['global_maximum_proven'])
        self.assertEqual(result['maintenance_lease_mode'], 'SHARED_READ_ONLY')
        self.assertEqual(observed['guard_samples'], 6)

    def test_media_or_guard_arrival_aborts_existing_probe_monitor(self):
        _, _, capacity = self.prepared()
        core, probe = capacity.helpers()
        core.services = Mock(return_value={'nox-media-comfyui': {'state': 'RUNNING'}})
        current = {'memory_current': 10, 'memory_max': 100, 'memory_high': None,
                   'cpu_quota_cores': 19.2, 'memory_events': {}}
        probe.resources = Mock(return_value=dict(current))
        capacity.helpers = Mock(return_value=(core, probe))
        observed = batch.configure_private_capacity(capacity, self.fake_guard())
        core.media_idle = Mock(side_effect=RuntimeError('WAIT_CAPACITY_MEDIA_ACTIVE'))
        core, probe = capacity.helpers()
        sample = probe.resources()
        with self.assertRaisesRegex(probe.Hold, 'OWNER_MEDIA_ARRIVED_OR_UNVERIFIED'):
            probe.resource_gate(sample)
        self.assertNotIn('prompt', str(sample).lower())
        # A separate fresh probe proves guard inhibition, without a latched media hold.
        _, _, capacity = self.prepared(); core, probe = capacity.helpers()
        core.services = Mock(return_value={'nox-media-comfyui': {'state': 'STOPPED'}})
        core.media_idle = Mock(return_value=None); probe.resources = Mock(return_value=dict(current))
        capacity.helpers = Mock(return_value=(core, probe))
        observed = batch.configure_private_capacity(capacity, self.fake_guard())
        observed.update(expected_guard_bindings={'fixture': 'binding'}, training_service={'state': 'RUNNING'})
        core, probe = capacity.helpers()
        with patch.object(batch, 'fresh_guard', side_effect=RuntimeError('WAIT_CURRENT_CAPACITY_GUARD_INHIBITED')):
            sample = probe.resources()
        with self.assertRaisesRegex(probe.Hold, 'GUARD_INHIBITED'):
            probe.resource_gate(sample)

    def test_media_busy_prevents_any_synthetic_inference(self):
        _, _, capacity = self.prepared(); core, probe = capacity.helpers()
        probe.infer = Mock()
        capacity.gate = Mock(side_effect=RuntimeError('WAIT_CAPACITY_MEDIA_ACTIVE'))
        batch.configure_private_capacity(capacity, self.fake_guard())
        with self.assertRaisesRegex(RuntimeError, 'WAIT_CAPACITY_MEDIA_ACTIVE'):
            capacity.run_series(core, probe, {'cases': []})
        probe.infer.assert_not_called()

    def test_actual_fair_receipt_shape_and_source_delta_are_required(self):
        row = {'schema': 'NOX_MEDIA_INBOX_FAIR_INSTALL_V1', 'request': batch.FAIR_CONTEXT['request'],
               'source_sha': batch.FAIR_CONTEXT['source_sha'], 'state': 'MEDIA_INBOX_FAIR_AND_REVIEWER_TRUTH_BOUND',
               'dispatcher_after_sha256': hashlib.sha256(b'dispatcher').hexdigest(),
               'training_identity_preserved': True, 'current_student_process_preserved': True}
        raw = json.dumps(row).encode()
        context = {**batch.FAIR_CONTEXT, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}
        core = types.SimpleNamespace(STATE=batch.ROOT / 'state', read=Mock(side_effect=[b'dispatcher', b'runtime', raw]))
        with patch.object(batch, 'DISPATCHER_SHA', row['dispatcher_after_sha256']), patch.object(batch, 'RUNTIME_SHA', hashlib.sha256(b'runtime').hexdigest()), patch.object(batch, 'FAIR_CONTEXT', context):
            value = batch.dispatcher_scope(core)
        self.assertEqual(value['fair_receipt_sha256'], context['receipt_sha256'])

    def test_unverified_training_still_observes_media_but_never_runs_capacity(self):
        training = types.SimpleNamespace(observe=Mock(return_value={'observation_completed': False}))
        media = types.SimpleNamespace(snapshot=Mock(return_value={'dispatcher_source': {}}))
        capacity = types.SimpleNamespace(main=Mock(side_effect=AssertionError('capacity called')))
        output = io.StringIO()
        with patch.object(batch, 'prepared', return_value=(training, media, capacity)), patch('sys.stdout', output):
            code = batch.main()
        self.assertEqual(code, 2)
        media.snapshot.assert_called_once(); capacity.main.assert_not_called()
        self.assertIn('WAIT_CURRENT_CAPACITY_TRAINING_OBSERVATION_UNVERIFIED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
