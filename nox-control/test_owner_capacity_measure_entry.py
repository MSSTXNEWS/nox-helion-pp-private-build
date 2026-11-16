import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('owner_capacity_measure_entry', HERE / 'owner_capacity_measure_entry.py')
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def bundle():
    return {'owner_capacity_probe.py': base64.b64encode((HERE / 'owner_capacity_probe.py').read_bytes()).decode(),
            'owner_plan_native_actions.py': base64.b64encode((HERE / 'owner_plan_native_actions.py').read_bytes()).decode()}


def profile(step=6, success=1, pid=42):
    return {'model': {'pid': 7}, 'workers': {'dispatcher': {'pid': 8}, 'config_sha256': 'a' * 64},
            'policy_sha256': 'b' * 64, 'source_pins': {'dispatcher': 'c' * 64},
            'training': {'process': {'pid': pid, 'start_ticks': 9}, 'lineage_sha256': 'd' * 64,
                         'admission_receipt_sha256': 'e' * 64, 'admission_pointer_sha256': 'f' * 64,
                         'global_step': step, 'successful_optimizer_steps': success, 'skipped_optimizer_steps': 0}}


class CapacityEntryTests(unittest.TestCase):
    def test_reviewed_sources_and_missing_context_are_fail_closed(self):
        self.assertEqual(a.digest((HERE / 'owner_capacity_probe.py').read_bytes()), a.PROBE_SHA)
        self.assertEqual(a.digest((HERE / 'hybrid_training_entry.py').read_bytes()), a.HYBRID_SHA)
        self.assertEqual(a.digest((HERE / 'owner_plan_native_actions.py').read_bytes()), a.ACTION_SHA)
        with patch.dict(os.environ, {}, clear=True), patch.object(a, 'native_profile') as inspect:
            with self.assertRaisesRegex(RuntimeError, 'OWNER_CONTEXT'):
                a.main()
            inspect.assert_not_called()
        with patch.object(a, 'BUNDLE', {'owner_capacity_probe.py': base64.b64encode(b'unreviewed').decode()}):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                a.load_probe()

    def test_foreground_slot_is_excluded_and_duty_services_are_not_invented_heavy_jobs(self):
        self.assertEqual(a.REQUESTED, (1, 2, 4, 5))
        self.assertNotIn('nox-agent-integrator-t859u', a.HEAVY + a.OPTIONAL_HEAVY)
        self.assertNotIn('nox-autoscale-t877u', a.HEAVY + a.OPTIONAL_HEAVY)
        self.assertIn('nox-agent-tuner-t858u', a.HEAVY)
        self.assertIn('nox-agent-architect-t859u', a.HEAVY)

    def test_normal_requires_same_run_and_successful_optimizer_progress(self):
        self.assertTrue(a.comparison(profile(), profile(7, 2), 'NORMAL')['optimizer_advanced'])
        self.assertFalse(a.comparison(profile(), profile(7, 1), 'NORMAL')['optimizer_advanced'])
        self.assertFalse(a.comparison(profile(), profile(7, 2, pid=43), 'NORMAL')['optimizer_advanced'])
        changed = profile(7, 2); changed['training']['admission_pointer_sha256'] = '1' * 64
        result = a.comparison(profile(), changed, 'NORMAL')
        self.assertFalse(result['profile_stable']); self.assertFalse(result['optimizer_advanced'])

    def test_quality_failure_does_not_become_a_quality_recommendation(self):
        with patch.object(a, 'BUNDLE', bundle()):
            probe = a.load_probe()
        rows = [{'concurrency': 5, 'state': 'QUALITY_FAILED', 'native_streams_completed': 12,
                 'samples': 12, 'hold_reason': None, 'p95_ttft_ms': 500, 'p95_total_ms': 2000,
                 'useful_tasks_per_sec': 3.0}]
        result = a.summarize(probe, rows, True)
        self.assertEqual(result['largest_latency_passing_transport_concurrency'], 5)
        self.assertIsNone(result['recommended_background_inferences'])
        self.assertFalse(result['quality_gate_passed']); self.assertFalse(result['global_maximum_proven'])
        self.assertFalse(result['mode_measurement_valid']); self.assertFalse(result['sweep_complete'])
        self.assertTrue(result['partial_case_evidence_usable'])
        self.assertFalse(a.summarize(probe, [], True)['mode_measurement_valid'])
        self.assertEqual(result['tested_concurrency'], [5])
        rows = [dict(rows[0], concurrency=count, state='PASSED', useful_tasks_per_sec=float(count)) for count in a.REQUESTED]
        self.assertEqual(a.summarize(probe, rows, True)['recommended_background_inferences'], 5)
        self.assertTrue(a.summarize(probe, rows, True)['sweep_complete'])
        self.assertIsNone(a.summarize(probe, rows, False)['recommended_background_inferences'])

    def test_model_text_is_withheld_even_for_a_public_fixture(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        body = ('data: ' + json.dumps({'choices': [{'delta': {'content': 'PRIVATE_MEMORY_TEXT'}, 'finish_reason': 'stop'}]})
                + '\n\ndata: [DONE]\n\n').encode()
        opener = Mock(); opener.open.return_value = Response(body)
        with patch.object(a, 'BUNDLE', bundle()), patch.object(a.urllib.request, 'build_opener', return_value=opener), patch.object(a, 'stop_active', return_value=False):
            probe = a.load_probe()
            row = probe.infer('/root/nox/models/current.gguf', 0, threading.Event(), time.monotonic() + 10)
        self.assertNotIn('PRIVATE_MEMORY_TEXT', json.dumps(row))
        self.assertNotIn('public_fixture_response', row)
        self.assertEqual(row['withheld_response_sample_sha256'], a.digest(b'PRIVATE_MEMORY_TEXT'))
        self.assertFalse(row['task_valid'])

    def test_media_admission_rejects_live_job_without_touching_gpu_or_auth(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)):
            directory = Path(tmp) / 'media/jobs'; directory.mkdir(parents=True)
            (directory / ('a' * 32 + '.json')).write_text(json.dumps({'state': 'RUNNING', 'request': {'prompt': 'PRIVATE_TEXT'}}))
            with patch.object(a, 'http_json') as http, patch.object(a.subprocess, 'run') as command:
                with self.assertRaisesRegex(RuntimeError, '^WAIT_CAPACITY_MEDIA_ACTIVE$'):
                    a.media_idle({'nox-media-comfyui': {'state': 'RUNNING'}})
                http.assert_not_called(); command.assert_not_called()

    def test_media_arrival_latches_cancellation_in_burst_monitor(self):
        probe = Mock()
        probe.Hold = RuntimeError
        probe.resources = Mock(return_value={'memory_current': 1})
        original_gate = Mock(); probe.resource_gate = original_gate
        with patch.object(a, 'media_idle', side_effect=RuntimeError('WAIT_CAPACITY_MEDIA_ACTIVE')):
            a.monitor_media(probe, {'media_engine_state': 'RUNNING'})
            sample = probe.resources()
            with self.assertRaisesRegex(RuntimeError, 'OWNER_MEDIA_ARRIVED'):
                probe.resource_gate(sample)
        original_gate.assert_called_once_with(sample, None)

    def test_boost_requires_real_gpu1_release(self):
        gpu = {'query_rc': 0, 'gpus': [{'index': 0, 'total_mib': 32495, 'free_mib': 10000},
                                     {'index': 1, 'total_mib': 32495, 'free_mib': 32000}]}
        a.hardware_gate(gpu, 'TASK_BOOST')
        gpu['gpus'][1]['free_mib'] = 12000
        with self.assertRaisesRegex(RuntimeError, 'GPU1_NOT_RELEASED'):
            a.hardware_gate(gpu, 'TASK_BOOST')
        a.hardware_gate(gpu, 'NORMAL')
        gpu['query_rc'] = 1
        with self.assertRaisesRegex(RuntimeError, 'TELEMETRY'):
            a.hardware_gate(gpu, 'NORMAL')

    def test_modes_preserve_prior_verified_measurement_and_unmeasured_normal(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)):
            first = {'requested_mode': 'TASK_BOOST', 'request': '6901234567', 'source': 'a' * 40,
                     'state': 'BOUNDED_MEASUREMENTS_COMPLETED', 'finished_at': time.time(),
                     'measured': {'mode_measurement_valid': True, 'recommended_background_inferences': 4}}
            a.save_modes(Path(tmp) / 'receipt1.json', 'b' * 64, first)
            file = Path(tmp) / 'owner_capacity/modes.json'
            value = a.document(file)
            self.assertEqual(value['modes']['NORMAL']['state'], 'AWAITING_RUNNING_OPTIMIZER_MEASUREMENT')
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            second = dict(first, request='6901234568', measured={'mode_measurement_valid': False})
            a.save_modes(Path(tmp) / 'receipt2.json', 'c' * 64, second)
            value = a.document(file)
            self.assertEqual(value['modes']['TASK_BOOST']['last_verified_measurement']['request'], first['request'])
            self.assertEqual(value['modes']['TASK_BOOST']['last_attempt']['request'], second['request'])
            self.assertFalse(value['control_settings_changed'])

    def test_sealed_admission_is_required_before_heartbeat_can_be_used(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'STATE', Path(tmp)), patch.object(a, 'SCRIPTS', Path(tmp)), patch.dict(os.environ, {}, clear=True):
            (Path(tmp) / 'hybrid_training_entry.py').write_bytes((HERE / 'hybrid_training_entry.py').read_bytes())
            (Path(tmp) / 'owner_training_admission.json').write_text(json.dumps({'schema': 'NOX_OWNER_TRAINING_ADMISSION_V1',
                'request': '6901234567', 'source_sha': 'a' * 40}))
            processes = {42: {'pid': 42, 'ppid': 1, 'script_names': {'hybrid_training_entry.py'}}}
            with self.assertRaisesRegex(RuntimeError, 'SEALED_TRAINING_ADMISSION'):
                a.training_evidence({a.TRAINER: {'state': 'RUNNING', 'pid': 42}}, processes)


if __name__ == '__main__':
    unittest.main()
