import base64
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('placement_tested', HERE/'owner_training_placement_recovery.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NAMES = ('trainer_state.json', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'adapter_config.json', 'adapter_model.safetensors')


class PlacementTests(unittest.TestCase):
    def setUp(self):
        m.BUNDLE = {'owner_training_amp_calibration.py': base64.b64encode((HERE/'owner_training_amp_calibration.py').read_bytes()).decode()}
        self.c = m.configure()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ('state', 'scripts', 'output'): (root/name).mkdir()
        for key, value in {'ROOT': root, 'STATE': root/'state', 'SCRIPTS': root/'scripts', 'OUTPUT': root/'output',
                           'POINTER': root/'state/pointer.json', 'WRAPPER': root/'scripts/wrapper.sh'}.items():
            setattr(self.c, key, value)
        lineage = {'schema': self.c.TRAIN_SCHEMA, 'fixture': True}
        (self.c.OUTPUT/'owner_lineage.json').write_text(json.dumps(lineage))
        self.c.LINEAGE_SHA = self.c.json_sha(lineage)
        self.recovery = types.SimpleNamespace(read=lambda p, *a: Path(p).read_bytes(),
            file_sha=lambda p, *a: m.digest(Path(p).read_bytes()), document=lambda p: json.loads(Path(p).read_bytes()))
        self.helper = types.SimpleNamespace(CHECKPOINT_NAMES=NAMES)
        self.baseline = self.checkpoint(5, 0, 0, 5, False)
        raw = json.dumps(self.baseline).encode()
        (self.c.OUTPUT/'owner_receipt_step_5.json').write_bytes(raw)
        self.c.BASELINE_RECEIPT_SHA = m.digest(raw)

    def checkpoint(self, step, start, good, skipped, changed):
        path = self.c.OUTPUT/f'checkpoint-{step}'
        path.mkdir(exist_ok=True)
        hashes = {}
        for name in NAMES:
            raw = json.dumps({'global_step': step}).encode() if name == 'trainer_state.json' else ('synthetic-'+name).encode()
            (path/name).write_bytes(raw)
            hashes[name] = m.digest(raw)
        return {'schema': self.c.TRAIN_SCHEMA, 'native_sha256': self.c.NATIVE_SHA, 'lineage_sha256': self.c.LINEAGE_SHA,
            'start_step': start, 'global_step': step, 'successful_optimizer_steps': good, 'skipped_optimizer_steps': skipped,
            'before_tensor_sha256': self.c.BASELINE_TENSOR_SHA, 'after_tensor_sha256': 'a'*64 if changed else self.c.BASELINE_TENSOR_SHA,
            'adapter_delta_verified': changed, 'loss': 1.5, 'merged': False, 'live_promoted': False,
            'checkpoint': {'path': str(path), 'global_step': step, 'files_sha256': hashes}}

    def positive(self):
        value = self.checkpoint(20, 5, 3, 12, True)
        value['checkpoint_restore'] = {'schema': 'NOX_LORA_INPLACE_CHECKPOINT_RESTORE_V1', 'global_step': 5, 'restored': True,
            'parameter_objects_preserved': True, 'base_placement_preserved': True, 'trainable_tensors': 66,
            'restored_tensor_sha256': self.c.BASELINE_TENSOR_SHA,
            'adapter_file_sha256': self.baseline['checkpoint']['files_sha256']['adapter_model.safetensors'],
            'optimizer_scheduler_scaler_rng_restore': 'DELEGATED_TO_HF_TRAINER'}
        return value

    def test_frozen_entry_new_source_and_short_observation_contract(self):
        self.assertEqual(m.digest((HERE/'owner_training_amp_calibration.py').read_bytes()), m.CALIBRATION_SHA)
        self.assertEqual(m.digest((HERE/'hybrid_training_entry.py').read_bytes()), m.NEW_HYBRID_SHA)
        self.assertEqual(m.digest((HERE/'owner_training_restore_preflight.py').read_bytes()), m.PREFLIGHT_SHA)
        self.assertIn(120, self.c.main.__code__.co_consts)
        self.assertNotIn(430, self.c.main.__code__.co_consts)
        self.assertEqual(self.c.calibration_metadata()['origin_admission'], self.c.ORIGIN)
        self.assertEqual(self.c.calibration_metadata()['hybrid_sha256'], m.NEW_HYBRID_SHA)

    def test_positive_requires_actual_restore_proof_and_preserves_zero_baseline(self):
        proof = self.c.checkpoint_proof(self.recovery, self.helper, self.baseline, baseline=True)
        self.assertFalse(proof['positive_optimizer_updates_verified'])
        value = self.positive()
        good = self.c.checkpoint_proof(self.recovery, self.helper, value)
        self.assertEqual(good['successful_optimizer_steps'], 3)
        self.assertTrue(good['checkpoint_restore_verified'])
        self.assertEqual(good['restored_checkpoint_step'], 5)
        value.pop('checkpoint_restore')
        with self.assertRaisesRegex(RuntimeError, 'RESTORE_NATIVE_PROOF'):
            self.c.checkpoint_proof(self.recovery, self.helper, value)

    def test_all_skipped_or_changed_base_is_not_success(self):
        zero = self.checkpoint(20, 5, 0, 15, False)
        with self.assertRaisesRegex(RuntimeError, 'NO_POSITIVE_OPTIMIZER_PROOF'):
            self.c.checkpoint_proof(self.recovery, self.helper, zero)
        value = self.positive()
        value['checkpoint_restore']['base_placement_preserved'] = False
        with self.assertRaisesRegex(RuntimeError, 'RESTORE_NATIVE_PROOF'):
            self.c.checkpoint_proof(self.recovery, self.helper, value)

    def test_changed_baseline_receipt_cannot_prove_restore(self):
        value = self.positive()
        (self.c.OUTPUT/'owner_receipt_step_5.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'RESTORE_BASELINE_CHANGED'):
            self.c.checkpoint_proof(self.recovery, self.helper, value)

    def test_complete_stop_scope_precedes_old_policy(self):
        stop = self.c.ROOT/'workspace_NOX_STOP'
        stop.write_bytes(b'')
        with patch.object(m, 'STOP_PATHS', (stop,)):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'):
                self.c.policy_admission(object(), object(), object())

    def test_observation_verifies_positive_without_any_restart(self):
        value = self.positive()
        value.update(state='VERIFIED_BOUNDED_ADAPTER_UPDATE', requested_step=20)
        (self.c.OUTPUT/'owner_last_result.json').write_text(json.dumps(value))
        pointer = {'request': '456', 'max_steps': 20, 'resume': True, 'sources': {}}
        self.c.POINTER.write_text(json.dumps(pointer))
        command = Mock(side_effect=AssertionError('observer must never start'))
        helper = types.SimpleNamespace(CHECKPOINT_NAMES=NAMES, command=command,
            atomic=lambda p, raw: p.write_bytes(raw), health=lambda: {'8081': 200},
            service_state=lambda: {'state': 'STOPPED'}, gpu=lambda: {}, progress=lambda: {'step': 20})
        loaded = {'owner_native_repair': helper, 'owner_training_resume': object(),
            'owner_training_recovery_entry': self.recovery, 'owner_training_disk_guard': object()}
        context = {'request': '456', 'source_sha': 'a'*40, 'receipt_sha256': 'b'*64}
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '789', 'NOX_OWNER_SOURCE_SHA': 'c'*40}), \
             patch.object(self.c, 'load', side_effect=lambda name: loaded[name]), \
             patch.object(self.c, 'policy_admission'), patch.object(self.c, 'sources_unchanged'), \
             patch.object(self.c, 'pending_evidence', return_value=({'baseline_saved_state': {}}, pointer, {'pid': 123})), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(self.c.main(context), 0)
        result = json.loads((self.c.STATE/'owner_maintenance_789.json').read_text())
        self.assertEqual(result['state'], self.c.VERIFIED)
        self.assertFalse(result['training_started'])
        self.assertFalse(result['continuation_to_1000_started'])
        self.assertEqual(result['adapter_placement_recovery'], m.placement_metadata())
        command.assert_not_called()


if __name__ == '__main__': unittest.main()
