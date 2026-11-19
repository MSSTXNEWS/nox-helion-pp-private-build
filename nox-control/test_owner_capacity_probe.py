"""Safety admission and measurement validity tests without a GPU or live chat."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('owner_capacity_probe', Path(__file__).with_name('owner_capacity_probe.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def stream(*objects, done=True):
    rows = ['data: ' + json.dumps(obj) + '\n\n' for obj in objects]
    if done:
        rows.append('data: [DONE]\n\n')
    return Response(''.join(rows).encode())


def sample(used=100, oom=0):
    return {'at_monotonic': time.monotonic(), 'cpu_quota_cores': 19.2,
            'memory_current': used, 'memory_max': 1000, 'memory_high': None,
            'memory_events': {'oom': oom, 'oom_kill': 0, 'max': 0},
            'cpu_stat': {'usage_usec': 1000}}


class CapacityProbeTests(unittest.TestCase):
    def test_explicit_model_port_is_bounded_to_existing_local_services(self):
        self.assertEqual(probe.model_base(8098), 'http://127.0.0.1:8098')
        self.assertEqual(probe.model_base(8081), probe.BASE)
        for value in (8080, 8082, 0, 65536, True, '8098', 'https://remote.invalid'):
            with self.assertRaisesRegex(probe.Hold, 'MODEL_PORT_SCOPE'):
                probe.model_base(value)

    def test_8098_inventory_uses_selected_service_without_inference(self):
        profile = {'verified': False, 'heartbeats': [], 'processes': []}
        with patch.object(probe, 'profile_evidence', return_value=profile), \
                patch.object(probe, 'source_proof', return_value={}), \
                patch.object(probe, 'resources', side_effect=sample), \
                patch.object(probe, 'gpu_snapshot', return_value={}), \
                patch.object(probe, 'stop_active', return_value=False), \
                patch.object(probe.urllib.request, 'urlopen', return_value=Response(b'[{"is_processing":false}]')) as request, \
                patch.object(probe, 'infer') as infer, contextlib.redirect_stdout(io.StringIO()):
            result = probe.main(['--mode', 'TASK_BOOST', '--inventory-only', '--model-port', '8098'])
        self.assertEqual(result['state'], 'INVENTORY_ONLY')
        self.assertEqual(result['model_port'], 8098)
        request.assert_called_once_with('http://127.0.0.1:8098/slots', timeout=2)
        infer.assert_not_called()
        self.assertEqual(probe.BASE, 'http://127.0.0.1:8081')

    def test_model_id_must_match_one_native_process_on_selected_port(self):
        model = '/root/nox/models/deepseek_v41_flash_iq2xxs/model-00001-of-00006.gguf'
        row = {'kind': 'model_service', 'pid': 42, 'start_ticks': '123',
               'port': '8098', 'model_path': model}
        self.assertEqual(probe.native_model_identity(model, 8098, [row])['pid'], 42)
        for rows in ([], [row, row], [{**row, 'port': '8081'}],
                     [{**row, 'kind': 'teacher_or_judge'}], [{**row, 'start_ticks': '0'}]):
            with self.assertRaises(probe.Hold):
                probe.native_model_identity(model, 8098, rows)
        with self.assertRaises(probe.Hold):
            probe.native_model_identity('/root/nox/models/current.gguf', 8098, [row])

    def test_selected_target_is_used_for_streaming_request(self):
        response = stream({'choices': [{'delta': {'content': '{"chat":8080,"engine":8081,"embeddings":8082}'}, 'finish_reason': 'stop'}]})
        with patch.object(probe.urllib.request, 'urlopen', return_value=response) as request, \
                patch.object(probe, 'stop_active', return_value=False):
            result = probe.infer('/root/nox/models/current.gguf', 0, threading.Event(),
                                 time.monotonic() + 20, base=probe.model_base(8098))
        self.assertEqual(result['state'], 'PASSED')
        self.assertEqual(request.call_args.args[0].full_url, 'http://127.0.0.1:8098/v1/chat/completions')

    def test_slots_reject_ambiguous_activity_without_exporting_prompt(self):
        for rows in ([], [{'is_processing': 0}], [{'processing': None}],
                     [{'is_processing': False, 'processing': True}], [{'prompt': 'private'}]):
            with self.assertRaises(probe.Hold):
                probe.slot_summary(rows)
        self.assertEqual(probe.slot_summary([{'is_processing': False, 'prompt': 'private'}]), {'slots': 1, 'busy': 0})
        self.assertEqual(probe.slot_summary([{'processing': True}]), {'slots': 1, 'busy': 1})

    def test_resource_gate_uses_cgroup_limit_and_oom_delta(self):
        with self.assertRaisesRegex(probe.Hold, 'HEADROOM'):
            probe.resource_gate(sample(used=920))
        with self.assertRaisesRegex(probe.Hold, 'OOM'):
            probe.resource_gate(sample(oom=1), sample())
        current = sample(used=600)
        current['memory_high'] = 650
        with self.assertRaisesRegex(probe.Hold, 'HEADROOM'):
            probe.resource_gate(current)

    def infer(self, response):
        with patch.object(probe.urllib.request, 'urlopen', return_value=response), patch.object(probe, 'stop_active', return_value=False):
            return probe.infer('/root/nox/models/current.gguf', 0, threading.Event(), time.monotonic() + 20)

    def test_native_usage_is_required_for_tokens_not_sse_chunk_count(self):
        frames = ({'choices': [{'delta': {'content': '{"chat":8080,'}}]},
                  {'choices': [{'delta': {'content': '"engine":8081,"embeddings":8082}'}, 'finish_reason': 'stop'}]})
        row = self.infer(stream(*frames))
        self.assertEqual(row['state'], 'PASSED')
        self.assertIsNone(row['completion_tokens'])
        self.assertEqual(row['token_source'], 'unavailable')
        row = self.infer(stream(*frames, {'choices': [], 'usage': {'completion_tokens': 23}}))
        self.assertEqual(row['completion_tokens'], 23)

    def test_remote_error_or_missing_done_is_not_a_success(self):
        frame = {'choices': [{'delta': {'content': '{"chat":8080,"engine":8081,"embeddings":8082}'}, 'finish_reason': 'stop'}]}
        self.assertEqual(self.infer(stream(frame, done=False))['state'], 'INVALID_OR_INCOMPLETE')
        self.assertEqual(self.infer(stream({'error': {'message': 'private error text'}}, frame))['state'], 'SSE_ERROR_OR_NONOBJECT')

    def test_correct_stream_with_wrong_answer_is_not_useful_work(self):
        row = self.infer(stream({'choices': [{'delta': {'content': '{"chat":9999}'}, 'finish_reason': 'stop'}]}))
        self.assertEqual(row['state'], 'INVALID_OR_INCOMPLETE')
        self.assertFalse(row['task_valid'])

    def test_recommendation_obeys_latency_and_uses_measured_configurations(self):
        rows = [{'concurrency': count, 'state': 'PASSED', 'useful_tasks_per_sec': rate,
                 'p95_ttft_ms': latency, 'p95_total_ms': 5000}
                for count, rate, latency in ((1, 1, 100), (2, 2.95, 500), (4, 3.0, 1000), (6, 4.0, 5000))]
        result = probe.recommend(rows, 3000, 12000)
        self.assertEqual(result['best_measured_concurrency'], 4)
        self.assertEqual(result['recommended_concurrency'], 2)
        self.assertEqual(result['largest_passing_tested_concurrency'], 4)
        self.assertIsNone(probe.recommend([], 3000, 12000)['best_measured_concurrency'])

    def test_boost_mode_does_not_hide_orphan_teacher_models(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / 'state').mkdir()
            (path / 'state/TRAIN_HOLD.flag').touch()
            statuses = '\n'.join(name + ' STOPPED Not started' for name in probe.HEAVY_SERVICES)
            with patch.object(probe, 'ROOT', path), patch.object(probe, 'run', return_value=(3, statuses)), patch.object(probe, 'process_evidence', return_value=[{'kind': 'teacher_or_judge', 'pid': 42}]):
                result = probe.profile_evidence('TASK_BOOST')
            self.assertFalse(result['verified'])
            self.assertIn('HEAVY_MODEL_PROCESSES_REMAIN', result['reasons'])

    def test_normal_mode_requires_actual_positive_step(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / 'status').mkdir()
            status = path / 'status/train_volta_t866u.json'
            status.write_text(json.dumps({'phase': 'train_owner_hybrid', 'step': 0}))
            with patch.object(probe, 'ROOT', path), patch.object(probe, 'run', return_value=(0, 'nox-train-volta-t866u RUNNING pid 22, uptime 0:01:00')), patch.object(probe, 'process_evidence', return_value=[{'kind': 'trainer', 'pid': 22}]):
                self.assertFalse(probe.profile_evidence('NORMAL')['verified'])
                status.write_text(json.dumps({'phase': 'train_owner_hybrid', 'step': 5}))
                self.assertTrue(probe.profile_evidence('NORMAL')['verified'])

    def test_burst_measures_same_six_tasks_and_never_invents_token_rate(self):
        lock = threading.Lock()
        state = {'active': 0, 'peak': 0}
        def fake_infer(model, index, cancel, deadline, usage, base=probe.BASE):
            with lock:
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
            time.sleep(0.02)
            with lock:
                state['active'] -= 1
            return {'state': 'PASSED', 'completion_tokens': None, 'ttft_ms': 1.0, 'total_ms': 20.0}
        with patch.object(probe, 'idle_gate'), patch.object(probe, 'resources', side_effect=sample), patch.object(probe, 'stop_active', return_value=False), patch.object(probe, 'infer', side_effect=fake_infer):
            result = probe.burst('fixture-model', 3, 6, time.monotonic() + 10, True)
        self.assertEqual(state['peak'], 3)
        self.assertEqual(result['passed'], 6)
        self.assertEqual(result['state'], 'PASSED')
        self.assertIsNone(result['completion_tokens_per_sec'])


if __name__ == '__main__':
    unittest.main()
