"""NOT PRODUCTION: synthetic tests; no cgroup/GPU/process reads or mutations."""
from __future__ import annotations

import copy
import unittest

import chat_resource_admission as admission


NOW = 1_795_057_000.0
MODEL_SHA = 'a' * 64
GPU0 = 'GPU-00000000-0000-0000-0000-000000000001'
GPU1 = 'GPU-00000000-0000-0000-0000-000000000002'


def sample(at, *, current=99_900_000_000, pss=18_000_000_000,
           rss=20_000_000_000, gpu_used=29_000_000_000,
           model_gpu=27_000_000_000, memory_psi=0.0, cpu_psi=0.0):
    return {
        'schema': admission.SAMPLE_SCHEMA,
        'observed_at': at,
        'instance_id': 60509551,
        'model': {'model_id': 'nox-ds41-8098', 'weights_sha256': MODEL_SHA,
                  'pid': 3266857, 'start_ticks': 172046662},
        'cgroup': {'memory_current_bytes': current, 'memory_max_bytes': 100_000_000_000,
                   'file_bytes': 85_000_000_000, 'inactive_file_bytes': 50_000_000_000,
                   'shmem_bytes': 15_000_000_000,
                   'memory_psi_some_avg10': memory_psi,
                   'memory_psi_full_avg10': 0.0, 'cpu_psi_some_avg10': cpu_psi},
        'process': {'pid': 3266857, 'start_ticks': 172046662,
                    'rss_bytes': rss, 'pss_bytes': pss},
        'gpus': [
            {'uuid': GPU0, 'total_bytes': 32_000_000_000, 'used_bytes': gpu_used,
             'model_process_bytes': model_gpu, 'process_pid': 3266857},
            {'uuid': GPU1, 'total_bytes': 32_000_000_000, 'used_bytes': 8_000_000_000,
             'model_process_bytes': 0, 'process_pid': 3266857},
        ],
    }


def valid_snapshot():
    return {
        'schema': admission.SCHEMA,
        'instance_id': 60509551,
        'model': {'model_id': 'nox-ds41-8098', 'weights_sha256': MODEL_SHA},
        'request': {'input_tokens': 2048, 'output_tokens': 512},
        'baseline': sample(NOW - 2, current=99_850_000_000, pss=17_900_000_000,
                           rss=19_900_000_000, gpu_used=28_900_000_000,
                           model_gpu=26_900_000_000),
        'current': sample(NOW - 1),
        'calibration': {
            'schema': admission.CALIBRATION_SCHEMA,
            'model_id': 'nox-ds41-8098', 'weights_sha256': MODEL_SHA,
            'measured_at': NOW - 100, 'sample_count': 3,
            'max_input_tokens': 4096, 'max_output_tokens': 1024,
            'peak_cgroup_delta_bytes': 4_000_000_000,
            'peak_pss_delta_bytes': 3_000_000_000,
            'peak_gpu_delta_bytes_by_uuid': {GPU0: 1_000_000_000, GPU1: 0},
        },
    }


POLICY = {'minimum_projected_headroom_bytes': 2 * admission.GIB,
          'minimum_gpu_free_bytes': 1 * admission.GIB,
          'maximum_memory_psi_avg10': 1.0,
          'maximum_cpu_psi_avg10': 50.0}


class ChatResourceAdmissionTests(unittest.TestCase):
    def test_low_raw_headroom_can_pass_only_on_measured_projected_cache(self):
        value = valid_snapshot()
        result = admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)
        self.assertEqual(result['state'], 'ELIGIBLE_PROJECTED_CACHE_RECLAIM')
        self.assertEqual(result['raw_headroom_bytes'], 100_000_000)
        self.assertEqual(result['reclaimable_file_bytes'], 50_000_000_000)
        self.assertGreater(result['projected_headroom_bytes'], POLICY['minimum_projected_headroom_bytes'])
        self.assertFalse(result['memory_reclaim_invoked'])
        self.assertEqual(value, valid_snapshot(), 'validator must not mutate caller evidence')

    def test_insufficient_projected_headroom_holds_with_clear_code(self):
        value = valid_snapshot()
        value['current']['cgroup']['inactive_file_bytes'] = 0
        with self.assertRaisesRegex(admission.ChatResourceHold, 'PROJECTED_HEADROOM'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)

    def test_missing_measurements_calibration_or_process_scoped_vram_hold(self):
        for edit, reason in (
            (lambda x: x.pop('current'), 'SNAPSHOT_FIELDS'),
            (lambda x: x['current']['process'].pop('pss_bytes'), 'PROCESS_FIELDS'),
            (lambda x: x['current']['gpus'][0].update(process_pid=9), 'GPU_PROCESS_IDENTITY'),
            (lambda x: x['calibration'].update(sample_count=2), 'IDENTITY_OR_COUNT'),
            (lambda x: x['calibration']['peak_gpu_delta_bytes_by_uuid'].pop(GPU1), 'CALIBRATION_GPU_SET'),
        ):
            value = valid_snapshot()
            edit(value)
            with self.subTest(reason=reason), self.assertRaisesRegex(admission.ChatResourceHold, reason):
                admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)

    def test_missing_or_stale_sample_and_calibration_hold(self):
        value = valid_snapshot()
        value['current']['observed_at'] = NOW - 6
        with self.assertRaisesRegex(admission.ChatResourceHold, 'CURRENT_STALE'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)
        value = valid_snapshot()
        value['calibration']['measured_at'] = NOW - admission.MAX_CALIBRATION_AGE_SECONDS - 1
        with self.assertRaisesRegex(admission.ChatResourceHold, 'CALIBRATION_STALE'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)

    def test_pressure_gpu_and_model_identity_gates_fail_closed(self):
        value = valid_snapshot()
        value['current']['cgroup']['memory_psi_some_avg10'] = 1.1
        with self.assertRaisesRegex(admission.ChatResourceHold, 'MEMORY_PRESSURE'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)
        value = valid_snapshot()
        value['calibration']['peak_gpu_delta_bytes_by_uuid'][GPU0] = 4_000_000_000
        with self.assertRaisesRegex(admission.ChatResourceHold, 'GPU_HEADROOM'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)
        value = valid_snapshot()
        value['current']['model']['start_ticks'] += 1
        with self.assertRaisesRegex(admission.ChatResourceHold, 'PROCESS_IDENTITY'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)

    def test_request_must_fit_calibrated_context_and_policy_is_required(self):
        value = valid_snapshot()
        value['request']['input_tokens'] = 8192
        with self.assertRaisesRegex(admission.ChatResourceHold, 'REQUEST_EXCEEDS'):
            admission.evaluate_chat_admission(value, policy=POLICY, now=NOW)
        with self.assertRaisesRegex(admission.ChatResourceHold, 'POLICY_FIELDS'):
            admission.evaluate_chat_admission(valid_snapshot(), policy={}, now=NOW)
        with self.assertRaisesRegex(admission.ChatResourceHold, 'POLICY_FIELDS'):
            admission.evaluate_chat_admission(valid_snapshot(), policy=None, now=NOW)


if __name__ == '__main__':
    unittest.main(verbosity=2)
