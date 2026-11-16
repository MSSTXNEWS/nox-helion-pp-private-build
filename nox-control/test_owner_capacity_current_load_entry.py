"""Offline current-load sweep contracts; no live model/GPU/service calls."""
import base64
from contextlib import nullcontext
import fcntl
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
from concurrent.futures import ThreadPoolExecutor


HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('current_load_entry', HERE / 'owner_capacity_current_load_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def bundle():
    return {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in entry.PINS}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def sse(text):
    rows = [{'choices': [{'delta': {'content': text}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'completion_tokens': 2}}]
    return Response((''.join('data: ' + json.dumps(row) + '\n\n' for row in rows) + 'data: [DONE]\n\n').encode())


def case(count, passed=5):
    return {'concurrency': count, 'samples': 6, 'completed_samples': 6,
            'native_streams_completed': 6, 'passed': passed,
            'state': 'PASSED' if passed == 6 else 'QUALITY_FAILED', 'hold_reason': None,
            'p95_ttft_ms': 400., 'p95_total_ms': 900., 'useful_tasks_per_sec': float(count)}


def snapshot():
    return {'chat_identity': {'pid': 7637, 'start_ticks': 149189867, 'model_slots': 6},
            'training_service': {'state': 'EXITED', 'pid': None},
            'resources': {}, 'model_slots': 6}


class CurrentLoadTests(unittest.TestCase):
    def helpers(self):
        with patch.object(entry, 'BUNDLE', bundle()):
            return entry.helpers()

    def fake_series(self, rows=None):
        core, probe = self.helpers()
        core.http_json = Mock(return_value={'data': [{'id': str(core.ROOT / 'models/current.gguf')}]})
        probe.infer = Mock(return_value={'state': 'PASSED', 'stream_done': True, 'finish_reason': 'stop', 'ttft_ms': 1.})
        probe.burst = Mock(side_effect=rows or [case(n) for n in entry.REQUESTED])
        return core, probe

    def test_pinned_helpers_import_without_native_io_and_preserve_oracle(self):
        with (patch.object(entry, 'BUNDLE', bundle()), patch('os.open', side_effect=AssertionError('native IO')),
              patch('subprocess.run', side_effect=AssertionError('service IO'))):
            core, probe = entry.helpers()
        self.assertEqual(probe.FIXTURES[2][2], 8)
        self.assertTrue(probe.validate_content(2, '8'))
        self.assertFalse(probe.validate_content(2, '11'))
        changed = bundle(); changed['owner_capacity_probe.py'] = base64.b64encode(b'pass').decode()
        with patch.object(entry, 'BUNDLE', changed), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            entry.helpers()

    def test_budget_categories_do_not_change_answer_or_export_content(self):
        _, probe = self.helpers()
        samples = [('8', 'VALID', 'INTEGER', 'MATCH', True),
                   ('11', 'VALID', 'INTEGER', 'MISMATCH', False),
                   ('8.0', 'VALID', 'FLOAT', 'TYPE_MISMATCH', False),
                   ('true', 'VALID', 'BOOLEAN', 'TYPE_MISMATCH', False),
                   ('8 GiB', 'INVALID', 'UNKNOWN', 'NOT_COMPARABLE', False),
                   ('NaN', 'INVALID', 'UNKNOWN', 'NOT_COMPARABLE', False),
                   ('```json\n8\n```', 'VALID', 'INTEGER', 'MATCH', True)]
        for text, parsed, kind, relation, good in samples:
            with (self.subTest(sample=text), patch.object(probe, 'stop_active', return_value=False),
                  patch.object(probe.urllib.request, 'urlopen', return_value=sse(text))):
                row = probe.infer('fixture-model', 2, threading.Event(), time.monotonic() + 10)
            self.assertEqual(row['state'], 'PASSED' if good else 'INVALID_OR_INCOMPLETE')
            self.assertNotIn('public_fixture_response', row)
            diagnostic = row['budget_validation']
            self.assertEqual((diagnostic['json_parse'], diagnostic['value_type'], diagnostic['value_relation']),
                             (parsed, kind, relation))
            self.assertEqual(diagnostic['oracle_match'], good)
            self.assertFalse(diagnostic['raw_response_exported'])
            self.assertFalse(diagnostic['actual_value_exported'])

    def test_parallel_diagnostics_are_request_local(self):
        _, probe = self.helpers()
        barrier = threading.Barrier(2); lock = threading.Lock(); answers = iter(('8', '11'))
        def response(*args, **kwargs):
            with lock:
                text = next(answers)
            barrier.wait(timeout=2)
            return sse(text)
        with patch.object(probe, 'stop_active', return_value=False), patch.object(probe.urllib.request, 'urlopen', side_effect=response):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(probe.infer, 'fixture', 2, threading.Event(), time.monotonic()+10) for _ in range(2)]
                rows = [future.result() for future in futures]
        self.assertEqual(sorted(row['budget_validation']['value_relation'] for row in rows), ['MATCH', 'MISMATCH'])
        for row in rows:
            self.assertEqual(row['state'] == 'PASSED', row['budget_validation']['oracle_match'])

    def test_quality_failure_continues_136_and_never_becomes_accepted_maximum(self):
        core, probe = self.fake_series()
        result = {'cases': []}
        with patch.object(entry, 'gate', side_effect=lambda *a, **k: snapshot()):
            entry.run_series(core, probe, result)
        self.assertEqual([call.args[1] for call in probe.burst.call_args_list], [1, 3, 6])
        self.assertEqual([row['foreground_spare_slots_during_case'] for row in result['cases']], [5, 3, 0])
        self.assertEqual(result['state'], 'CURRENT_LOAD_MEASURED_WITH_QUALITY_FAILURES')
        self.assertTrue(result['measured']['sweep_complete'])
        self.assertIsNone(result['measured']['recommended_tested_total_concurrency'])
        self.assertEqual(result['measured']['largest_latency_passing_tested_concurrency'], 6)
        for key in ('normal_mode_proven', 'task_boost_mode_proven', 'global_maximum_proven', 'sustained_capacity_proven'):
            self.assertFalse(result['measured'][key])
        self.assertIsNone(entry.summary(probe, [case(1, 5), case(3, 6), case(6, 6)], True)['recommended_tested_total_concurrency'])

    def test_busy_before_next_case_returns_wait_without_new_requests(self):
        core, probe = self.fake_series()
        result = {'cases': []}
        calls = [snapshot(), snapshot(), snapshot(), RuntimeError('CHAT_BUSY')]
        with patch.object(entry, 'gate', side_effect=calls):
            with self.assertRaisesRegex(RuntimeError, 'CHAT_BUSY') as caught:
                entry.run_series(core, probe, result)
        self.assertEqual(entry.safe_error(caught.exception), 'WAIT_CURRENT_LOAD_CHAT_BUSY')
        self.assertEqual([call.args[1] for call in probe.burst.call_args_list], [1])
        self.assertFalse(entry.summary(probe, result['cases'], False)['sweep_complete'])

    def test_transport_or_pressure_failure_stops_sweep(self):
        failed = dict(case(1), state='FAILED', hold_reason='MEMORY_PRESSURE_OOM', native_streams_completed=4)
        core, probe = self.fake_series([failed])
        result = {'cases': []}
        with patch.object(entry, 'gate', side_effect=lambda *a, **k: snapshot()), self.assertRaisesRegex(RuntimeError, 'TRANSPORT_OR_RESOURCE'):
            entry.run_series(core, probe, result)
        self.assertEqual(probe.burst.call_count, 1)
        self.assertFalse(entry.summary(probe, result['cases'], False)['sweep_complete'])

    def test_stop_busy_and_ram_gate_precede_model_work(self):
        core, probe = self.helpers()
        probe.idle_gate = Mock(return_value={'slots': 6, 'busy': 0})
        probe.resources = Mock(return_value={})
        probe.resource_gate = Mock(side_effect=RuntimeError('HOLD_RAM_PRESSURE'))
        core.services = Mock(side_effect=AssertionError('must not inspect later services'))
        with patch.object(entry, 'global_stop', return_value=True), patch.object(entry, 'chat_identity', side_effect=AssertionError('must stop first')):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'):
                entry.gate(core, probe)
        with patch.object(entry, 'global_stop', return_value=False), patch.object(entry, 'chat_identity', return_value=snapshot()['chat_identity']):
            probe.idle_gate.return_value = {'slots': 6, 'busy': 1}
            with self.assertRaisesRegex(RuntimeError, 'CHAT_BUSY'):
                entry.gate(core, probe)
            probe.idle_gate.return_value = {'slots': 6, 'busy': 0}
            with self.assertRaisesRegex(RuntimeError, 'RAM_PRESSURE'):
                entry.gate(core, probe)
        core.services.assert_not_called()

    def test_existing_lease_never_creates_missing_file_and_respects_holder(self):
        with tempfile.TemporaryDirectory() as root:
            core = types.SimpleNamespace(STATE=Path(root), checked=lambda p: p)
            with self.assertRaises(FileNotFoundError), entry.existing_lease(core):
                pass
            self.assertEqual(list(Path(root).iterdir()), [])
            path = Path(root)/'owner_maintenance.lock'; path.write_bytes(b''); path.chmod(0o600)
            fd = os.open(path, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, 'WAIT_CURRENT_LOAD_OWNER_LEASE_BUSY'), entry.existing_lease(core):
                    pass
            finally:
                os.close(fd)
            before = path.stat()
            with entry.existing_lease(core):
                pass
            self.assertEqual((before.st_size, before.st_mtime_ns), (path.stat().st_size, path.stat().st_mtime_ns))

    def test_main_quality_measurement_not_successful_quality_acceptance(self):
        core, probe = self.fake_series()
        output = io.StringIO()
        with (patch.object(entry, 'helpers', return_value=(core, probe)), patch.object(entry, 'existing_lease', return_value=nullcontext()),
              patch.object(entry, 'gate', side_effect=lambda *a, **k: snapshot()),
              patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '6907999999', 'NOX_OWNER_SOURCE_SHA': 'a'*40}),
              patch('sys.stdout', output)):
            code = entry.main()
        self.assertEqual(code, 0)
        line = next(line for line in output.getvalue().splitlines() if line.startswith('NOX_MAINT_REPAIR='))
        result = json.loads(line.split('=',1)[1])['data']
        self.assertEqual(result['state'], 'CURRENT_LOAD_MEASURED_WITH_QUALITY_FAILURES')
        self.assertIsNone(result['measured']['recommended_tested_total_concurrency'])
        self.assertFalse(result['measurement_files_written'])
        self.assertFalse(result['training_flags_written'])
        self.assertFalse(result['full_process_inventory_performed'])
        self.assertNotIn('PRIVATE', entry.safe_error(RuntimeError('PRIVATE user content')))


if __name__ == '__main__':
    unittest.main()
