"""Synthetic file/receipt tests; no model, GPU, network or native process calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


OBS = module(HERE / 'owner_qwen_training_observe.py', 'qwen_observe_test')
CONTRACT_PATH = Path('/tmp/nox_qwen_owner_qwen_training_contract.py')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    path.write_bytes(raw)
    return sha(raw)


class QwenObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The fixture executes the exact public pure contract, never student code.
        raw = CONTRACT_PATH.read_bytes()
        assert sha(raw) == OBS.PINS['owner_qwen_training_contract.py']
        cls.contract = module(CONTRACT_PATH, 'qwen_contract_test')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / 'output'
        self.output.mkdir()
        self.scope = patch.object(OBS, 'OUTPUT', self.output)
        self.scope.start()

    def tearDown(self):
        self.scope.stop()
        self.temp.cleanup()

    def fixture(self, good=5, skipped=2):
        c = self.contract
        lineage = {'schema': c.SCHEMA, 'base': {'model_id': c.MODEL_ID, 'revision': c.REVISION,
            'manifest_sha256': c.MANIFEST_SHA, 'verified_files': 16, 'verified_bytes': 19_329_393_661,
            'full_base_sha256_verified': True}, 'entry_sha256': OBS.PINS['qwen_student_training_entry.py'],
            'contract_sha256': OBS.PINS['owner_qwen_training_contract.py'],
            'memfd_source_sha256': OBS.PINS['owner_qwen_memfd.py'],
            'train_sha256': OBS.DATA_PINS['train.jsonl'], 'holdout_sha256': OBS.DATA_PINS['holdout.jsonl'],
            'dataset_manifest_sha256': OBS.DATA_PINS['corpus_manifest.json'], 'runtime_versions': {'test': True},
            'target_names': list(c.text_projection_names()),
            'targets': {'tensors': 496, 'parameters': 32, 'dtype': 'float32'},
            'precision': 'NF4_FP16_FP32_LORA', 'optimizer': 'AdamW_UNFUSED_FP32',
            'accumulation': 8, 'sequence_length': 512, 'planned_updates': 50_000}
        updates = [{'optimizer_step_before': i, 'optimizer_step_after': i + 1,
                    'adapter_sha_before': sha(('tensor' + str(i)).encode()),
                    'adapter_sha_after': sha(('tensor' + str(i + 1)).encode()),
                    'amp_skipped': False, 'finite_gradients': True, 'loss': 1.0,
                    'training_example_sha256': [sha(('example' + str(i * 8 + j)).encode()) for j in range(8)]}
                   for i in range(good)]
        state = {'successful_total': good, 'attempted_total': good + skipped, 'skipped_total': skipped,
                 'initial_holdout_loss': 1.1, 'last_holdout_loss': 1.0,
                 'holdout_evaluated_successful_total': good, 'update_evidence': updates}
        directory = self.output / ('checkpoint-u%08d-a%08d-g%020d' % (good, good + skipped, 123))
        directory.mkdir()
        for name in OBS.REQUIRED:
            (directory / name).write_bytes(b'synthetic-owned-checkpoint-fixture')
        write(directory / 'lineage.json', lineage)
        write(directory / 'student_state.json', state)
        process = {'pid': 1234, 'start_ticks': 5678, 'boot_id': '00000000-0000-0000-0000-000000000000'}
        manifest = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': directory.name,
                    'successful_total': good, 'attempted_total': good + skipped,
                    'lineage_sha256': c.canonical_sha(lineage),
                    'adapter_tensor_sha256': updates[-1]['adapter_sha_after'] if updates else sha(b'tensor0'),
                    'holdout_evaluated_successful_total': good, 'holdout_loss': 1.0,
                    'files_sha256': {p.name: sha(p.read_bytes()) for p in directory.iterdir()},
                    'process_identity': process}
        manifest_sha = write(directory / 'checkpoint_manifest.json', manifest)
        write(self.output / 'latest_checkpoint.json', {'directory': directory.name, 'manifest_sha256': manifest_sha})
        terminal = {'schema': c.PROOF_SCHEMA, 'state': 'STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED',
                    'lineage_sha256': c.canonical_sha(lineage), 'base_manifest_sha256': c.MANIFEST_SHA,
                    'successful_optimizer_steps': good, 'attempted_steps': good + skipped, 'skipped_steps': skipped,
                    'update_evidence': updates, 'final_adapter_tensor_sha256': manifest['adapter_tensor_sha256'],
                    'checkpoint': str(directory), 'checkpoint_manifest_sha256': manifest_sha,
                    'reload_verified': False, 'holdout_finite': True, 'independent_holdout_accepted': True,
                    'holdout_evaluated_successful_total': good, 'initial_holdout_loss': 1.1,
                    'final_holdout_loss': 1.0, 'process_identity': process}
        write(self.output / 'owner_last_result.json', terminal)
        return lineage, state, manifest, terminal, directory

    def test_five_real_deltas_checkpointed_are_not_restart_acceptance(self):
        lineage, state, manifest, _, _ = self.fixture()
        result, _, _ = OBS.checkpoint_proof(self.contract, lineage, time.monotonic() + 10)
        self.assertEqual(result['successful_optimizer_steps'], 5)
        self.assertTrue(result['all_manifest_files_sha256_verified'])
        self.assertEqual(len(result['files']), 9)
        terminal = OBS.terminal_proof(self.output / 'owner_last_result.json', self.contract, lineage, manifest, state)
        self.assertFalse(terminal['restart_acceptance_verified'])
        self.assertFalse(terminal['reload_verified'])
        with self.assertRaisesRegex(OBS.Hold, 'RESTART_ACCEPTANCE'):
            OBS.terminal_proof(self.output / 'owner_last_result.json', self.contract, lineage, manifest, state, acceptance=True)

    def test_counter_and_nonzero_origin_fabrication_rejected(self):
        _, state, _, _, _ = self.fixture()
        state['attempted_total'] += 1
        with self.assertRaisesRegex(OBS.Hold, 'UPDATE_COUNTERS'):
            OBS.update_chain(state, self.contract)
        state['attempted_total'] -= 1
        state['update_evidence'][0]['optimizer_step_before'] = 4
        state['update_evidence'][0]['optimizer_step_after'] = 5
        with self.assertRaisesRegex(OBS.Hold, 'UPDATE_CHAIN'):
            OBS.update_chain(state, self.contract)

    def test_checkpoint_hash_change_and_missing_rng_rejected(self):
        lineage, _, _, _, directory = self.fixture()
        (directory / 'optimizer.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(OBS.Hold, 'FILE_SHA'):
            OBS.checkpoint_proof(self.contract, lineage, time.monotonic() + 10)
        (directory / 'rng_state.pt').unlink()
        with self.assertRaisesRegex(OBS.Hold, 'CHECKPOINT_CONTENTS'):
            OBS.checkpoint_proof(self.contract, lineage, time.monotonic() + 10)

    def test_zero_skipped_checkpoint_does_not_claim_updates(self):
        lineage, _, _, _, _ = self.fixture(good=0, skipped=8)
        result, _, _ = OBS.checkpoint_proof(self.contract, lineage, time.monotonic() + 10)
        self.assertEqual(result['successful_optimizer_steps'], 0)
        self.assertFalse(result['positive_optimizer_updates_verified'])

    def test_six_and_restart_contract_pass_only_with_matching_holdout(self):
        lineage, state, manifest, terminal, _ = self.fixture(good=6)
        terminal.update(state='STUDENT_RESTART_AND_UPDATES_VERIFIED', reload_verified=True)
        path = self.output / 'owner_acceptance.json'
        write(path, terminal)
        accepted = OBS.terminal_proof(path, self.contract, lineage, manifest, state, acceptance=True)
        self.assertTrue(accepted['restart_acceptance_verified'])
        terminal['final_holdout_loss'] = 9.0
        write(path, terminal)
        with self.assertRaisesRegex(OBS.Hold, 'TERMINAL_HOLDOUT'):
            OBS.terminal_proof(path, self.contract, lineage, manifest, state, acceptance=True)

    def test_checkpoint_pointer_replaced_during_rehash_fails_closed(self):
        lineage, _, _, _, _ = self.fixture()
        pointer = self.output / 'latest_checkpoint.json'
        original = OBS.document
        pointer_reads = []

        def advance_during_read(path, expected=None):
            if Path(path) == pointer:
                pointer_reads.append(1)
                if len(pointer_reads) == 2:
                    write(pointer, {
                        'directory': 'checkpoint-u00000007-a00000007-g00000000000000000123',
                        'manifest_sha256': '0' * 64
                    })
            return original(path, expected)

        with patch.object(OBS, 'document', side_effect=advance_during_read):
            with self.assertRaisesRegex(OBS.Hold, 'CHECKPOINT_POINTER_CHANGED'):
                OBS.checkpoint_proof(self.contract, lineage, time.monotonic() + 10)
        self.assertEqual(len(pointer_reads), 2)

    def test_wrong_contract_bytes_never_execute(self):
        scripts = Path(self.temp.name) / 'scripts'; scripts.mkdir()
        marker = Path(self.temp.name) / 'executed'
        (scripts / 'owner_qwen_training_contract.py').write_text('open(' + repr(str(marker)) + ', "w").write("bad")')
        with patch.object(OBS, 'SCRIPTS', scripts), self.assertRaisesRegex(OBS.Hold, 'FILE_SHA'):
            OBS.load_contract()
        self.assertFalse(marker.exists())

    def test_fifo_and_duplicate_json_are_bounded_rejections(self):
        fifo = Path(self.temp.name) / 'fifo'; os.mkfifo(fifo)
        with self.assertRaisesRegex(OBS.Hold, 'FILE_BOUND'):
            OBS.read(fifo)
        duplicate = Path(self.temp.name) / 'duplicate.json'
        duplicate.write_text('{"good": 0, "good": 5}')
        with self.assertRaisesRegex(OBS.Hold, 'JSON_DUPLICATE'):
            OBS.document(duplicate)

    def test_lineage_load_is_source_bound_and_does_not_read_base(self):
        lineage, _, _, _, _ = self.fixture()
        value = OBS.lineage_proof(lineage, self.contract, {'runtime_versions': {'test': True}})
        self.assertTrue(value['full_model_load_evidence_verified'])
        self.assertFalse(value['base_files_rehashed_by_observer'])
        lineage['entry_sha256'] = '0' * 64
        with self.assertRaisesRegex(OBS.Hold, 'LINEAGE_SOURCE'):
            OBS.lineage_proof(lineage, self.contract, {'runtime_versions': {'test': True}})


if __name__ == '__main__':
    unittest.main()
