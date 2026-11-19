"""Focused control-flow/state-continuity fixtures; no native CUDA or model load."""
import ast
import copy
from contextlib import ExitStack, nullcontext
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ORIGINAL = Path('/tmp/nox_qwen_qwen_student_training_entry.py')
DEPENDENCIES = {
    'owner_qwen_training_contract': (Path('/tmp/nox_qwen_owner_qwen_training_contract.py'),
        '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a'),
    'owner_qwen_memfd': (Path('/tmp/nox_qwen_owner_qwen_memfd.py'),
        '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82'),
}
with patch.dict(sys.modules):
    for name, (path, pin) in DEPENDENCIES.items():
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin:
            raise RuntimeError('Fixture dependency changed')
        value = types.ModuleType(name); value.__file__ = str(path)
        sys.modules[name] = value
        exec(compile(raw, str(path), 'exec'), value.__dict__)

    spec = importlib.util.spec_from_file_location('_student_revision_fixture', HERE / 'qwen_student_training_entry_revision.py')
    S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)


class Tensor:
    def __init__(self, raw, dtype='uint8', shape=None):
        self.raw = bytes(raw); self.dtype = dtype
        self.shape = shape if shape is not None else (len(self.raw) // self.element_size(),)

    def element_size(self):
        return {'uint8': 1, 'int64': 8, 'float32': 4}[self.dtype]

    def numel(self):
        return len(self.raw) // self.element_size()

    def detach(self): return self
    def contiguous(self): return self
    def cpu(self): return self
    def numpy(self): return self
    def tobytes(self): return self.raw
    def reshape(self, *_): return Tensor(self.raw, self.dtype)
    def view(self, dtype): return Tensor(self.raw, dtype)
    def __getitem__(self, key): return Tensor(self.raw[key], self.dtype)


class Loss:
    def __init__(self, value): self.value = value
    def float(self): return self
    def __float__(self): return self.value


class Torch:
    uint8 = 'uint8'; float16 = 'float16'

    def __init__(self):
        self.cpu_state = 17; self.cuda_state = [23]
        self.cuda = types.SimpleNamespace(get_rng_state_all=self.cuda_get, set_rng_state_all=self.cuda_set)

    def get_rng_state(self): return Tensor(struct.pack('<q', self.cpu_state), 'int64')
    def set_rng_state(self, tensor): self.cpu_state = struct.unpack('<q', tensor.raw)[0]
    def cuda_get(self): return [Tensor(struct.pack('<q', n), 'int64') for n in self.cuda_state]
    def cuda_set(self, tensors): self.cuda_state = [struct.unpack('<q', n.raw)[0] for n in tensors]
    def is_tensor(self, value): return isinstance(value, Tensor)
    def isfinite(self, value): return math.isfinite(float(value))
    def inference_mode(self): return nullcontext()
    def autocast(self, *_a, **_k): return nullcontext()
    def save(self, value, path): Path(path).write_bytes(b'synthetic-serialized-state')


class Stateful:
    def __init__(self, value): self.value = value
    def state_dict(self): return self.value


class Model:
    def __init__(self, torch, on_call=None):
        self.torch = torch; self.training = True; self.calls = 0; self.on_call = on_call

    def eval(self): self.training = False
    def train(self, mode=True): self.training = mode

    def __call__(self, **_):
        self.calls += 1
        self.torch.cpu_state += 1; self.torch.cuda_state[0] += 3; random.random()
        if self.on_call: self.on_call(self.calls)
        return types.SimpleNamespace(loss=Loss(1.0 + self.calls / 1000))

    def save_pretrained(self, path, **_):
        for name in ('adapter_model.safetensors', 'adapter_config.json', 'README.md'):
            (path / name).write_bytes(b'synthetic-' + name.encode())


def state():
    return {'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0, 'data_cursor': 200,
            'initial_holdout_loss': 1.52, 'last_holdout_loss': 1.26,
            'holdout_evaluated_successful_total': 10, 'update_evidence': [{'fixture': 'hash-only'}]}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.torch = Torch(); self.saved = state()
        self.optimizer = Stateful({'state': {0: {'step': 25, 'moment': Tensor(struct.pack('<f', 1.0), 'float32')}},
                                   'param_groups': [{'params': [0], 'lr': 0.00005}]})
        self.scheduler = Stateful({'last_epoch': 25, '_step_count': 26})
        self.scaler = Stateful({'scale': 1.0, '_growth_tracker': 25})
        self.model = Model(self.torch)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(S, 'adapter_hash', return_value='a' * 64))
        self.stack.enter_context(patch.object(S, 'optimizer_step_number', return_value=25))
        self.stack.enter_context(patch.object(S, 'frozen_batch', return_value={}))
        self.stack.enter_context(patch.object(S, 'stop_reason', return_value=None))
        self.addCleanup(self.stack.close)
        self.python_rng = random.getstate()
        self.addCleanup(random.setstate, self.python_rng)

    def evaluate(self):
        return S.evaluate(self.model, None, list(range(16)), self.torch, optimizer=self.optimizer,
                          scheduler=self.scheduler, scaler=self.scaler, state=self.saved)

    def test_sixteen_forwards_preserve_all_semantic_state_and_rng(self):
        before = copy.deepcopy(self.saved)
        result = self.evaluate()
        self.assertEqual(self.model.calls, 16)
        self.assertTrue(self.model.training)
        self.assertEqual(result['example_count'], 16)
        self.assertEqual(result['before'], result['after'])
        self.assertEqual(self.saved, before)
        self.assertEqual(self.torch.cpu_state, 17)
        self.assertEqual(self.torch.cuda_state, [23])
        self.assertEqual(random.getstate(), self.python_rng)

    def test_optimizer_moment_mutation_is_rejected_even_with_same_step(self):
        self.model.on_call = lambda n: self.optimizer.value['state'][0].update(
            moment=Tensor(struct.pack('<f', 2.0), 'float32')) if n == 8 else None
        with self.assertRaisesRegex(S.Hold, 'CHANGED_TRAINING_STATE'):
            self.evaluate()
        self.assertEqual(self.torch.cpu_state, 17)
        self.assertEqual(random.getstate(), self.python_rng)

    def test_update_evidence_mutation_is_rejected(self):
        self.model.on_call = lambda n: self.saved['update_evidence'].append({'wrong': n}) if n == 4 else None
        with self.assertRaisesRegex(S.Hold, 'CHANGED_TRAINING_STATE'):
            self.evaluate()

    def test_exception_restores_rng_and_original_eval_mode(self):
        self.model.training = False
        def fail(n):
            if n == 3: raise RuntimeError('synthetic forward failure')
        self.model.on_call = fail
        with self.assertRaisesRegex(RuntimeError, 'synthetic forward'):
            self.evaluate()
        self.assertFalse(self.model.training)
        self.assertEqual(self.torch.cpu_state, 17)
        self.assertEqual(self.torch.cuda_state, [23])
        self.assertEqual(random.getstate(), self.python_rng)

    def test_media_yield_between_rows_restores_rng_and_does_not_commit_metrics(self):
        before = copy.deepcopy(self.saved)
        with patch.object(S, 'stop_reason', side_effect=lambda: 'EXISTING_TRAINER_HOLD_OR_PAUSE' if self.model.calls >= 4 else None):
            with self.assertRaisesRegex(S.EvaluationYield, 'HOLD_OR_PAUSE'):
                self.evaluate()
        self.assertEqual(self.model.calls, 4)
        self.assertEqual(self.saved, before)
        self.assertEqual(random.getstate(), self.python_rng)

    def test_stop_before_first_row_never_calls_model(self):
        with patch.object(S, 'stop_reason', return_value='MANUAL_OWNER_STOP'):
            with self.assertRaisesRegex(S.EvaluationYield, 'MANUAL_OWNER_STOP'):
                self.evaluate()
        self.assertEqual(self.model.calls, 0)

    def test_eight_rows_cannot_be_claimed_as_full_holdout(self):
        with self.assertRaisesRegex(S.Hold, 'HOLDOUT_COUNT'):
            S.evaluate(self.model, None, list(range(8)), self.torch, optimizer=self.optimizer,
                       scheduler=self.scheduler, scaler=self.scaler, state=self.saved)

    def test_scheduler_is_independent_of_frequent_checkpoint_save_clock(self):
        self.saved['holdout_evaluated_successful_total'] = 25
        self.saved['successful_total'] = 30
        # A checkpoint at monotonic399 must not move evaluation time100.
        self.assertFalse(S.evaluation_due(self.saved, 1000, 100, now=399))
        self.assertTrue(S.evaluation_due(self.saved, 1000, 100, now=400))
        self.saved['successful_total'] = 35
        self.assertTrue(S.evaluation_due(self.saved, 1000, 100, now=101))
        self.saved['successful_total'] = 1000
        self.saved['holdout_evaluated_successful_total'] = 999
        self.assertTrue(S.evaluation_due(self.saved, 1000, 100, now=101))


class CheckpointBarrierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.state = state(); self.torch = Torch(); self.model = Model(self.torch)
        self.optimizer = Stateful({}); self.scheduler = Stateful({}); self.scaler = Stateful({})
        self.lineage = {'fixture': 'origin'}
        self.binding = {'schema': 'NOX_QWEN_EXECUTION_BINDING_V1', 'runtime_entry_sha256': 'e' * 64}
        self.identity = {'pid': 1234, 'start_ticks': 4567, 'boot_id': 'a' * 36}
        self.restored = {'directory': 'checkpoint-u00000025-a00000025-g00000000000000000001',
                         'manifest_sha256': 'b' * 64, 'student_state_sha256': 'c' * 64, 'successful_total': 25}
        self.measured = {'loss': 1.25, 'example_count': 16, 'before': {'step': 25}, 'after': {'step': 25},
                         'started_at': 10.0, 'finished_at': 12.0, 'finished_monotonic': 100.0}
        self.events = []; self.invalid_permission = False
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(S, 'EXECUTION_CONTEXT', {'fixture': True}))
        self.stack.enter_context(patch.object(S, 'execution_call', side_effect=self.call))
        self.stack.enter_context(patch.object(S, 'check_resources'))
        self.stack.enter_context(patch.object(S, 'prune_checkpoints', side_effect=lambda *_: self.events.append('prune')))
        self.stack.enter_context(patch.object(S, 'adapter_hash', return_value='a' * 64))
        self.stack.enter_context(patch.object(S, 'process_identity', return_value=self.identity))
        self.stack.enter_context(patch.object(S, 'stop_reason', return_value=None))

    def call(self, name, *args, **kwargs):
        if name == 'execution_binding': return copy.deepcopy(self.binding)
        if name in ('checkpoint_binding', 'bootstrap_evaluation_proof'):
            _ctx, manifest, saved = args
            path = self.output / manifest['directory']
            self.assertEqual(json.loads((path / 'checkpoint_manifest.json').read_text()), manifest)
            self.assertEqual(json.loads((path / 'student_state.json').read_text()), saved)
            self.assertEqual(len(manifest['files_sha256']), 10)
            self.assertEqual(manifest['execution_binding'], self.binding)
            self.events.append(name)
            return {'verified': True}
        if name == 'wait_for_optimizer_permission':
            _ctx, manifest, saved = args
            pointer = json.loads((self.output / 'latest_checkpoint.json').read_text())
            progress = json.loads((self.output / 'owner_progress.json').read_text())
            self.assertEqual(pointer['directory'], manifest['directory'])
            self.assertEqual(saved['successful_total'], 25)
            self.assertEqual(progress['state'], 'NATIVE_EXECUTION_EVALUATION_CHECKPOINTED')
            self.assertFalse(progress['optimizer_permission_verified'])
            self.assertEqual(saved['last_evaluation_witness']['before'], saved['last_evaluation_witness']['after'])
            self.events.append(name)
            return {'state': 'OPTIMIZER_PERMISSION_VERIFIED', 'optimizer_allowed': not self.invalid_permission,
                    'checkpoint_manifest_sha256': pointer['manifest_sha256'], 'process_identity': self.identity}
        raise AssertionError(name)

    def prepare(self, kind='BOOTSTRAP_RESTORE'):
        return S.evaluation_checkpoint_and_permission(
            self.output, self.model, self.optimizer, self.scheduler, self.scaler, self.state, self.lineage,
            self.torch, self.measured, kind, self.restored)

    def test_same_counter_ten_payload_files_and_progress_exist_before_permission(self):
        result = self.prepare()
        self.assertIsNone(result['reason'])
        self.assertEqual(result['last_evaluation_finished'], 100)
        self.assertLess(self.events.index('checkpoint_binding'), self.events.index('wait_for_optimizer_permission'))
        self.assertLess(self.events.index('bootstrap_evaluation_proof'), self.events.index('wait_for_optimizer_permission'))
        self.assertEqual(self.state['successful_total'], 25)
        self.assertEqual(self.state['attempted_total'], 25)
        self.assertEqual(self.state['data_cursor'], 200)
        self.assertEqual(len(list(result['checkpoint'].iterdir())), 11)  # 10 payload files plus manifest.

    def test_false_permission_is_categorical_hold_without_update(self):
        self.invalid_permission = True
        result = self.prepare()
        self.assertEqual(result['reason'], 'HOLD_OPTIMIZER_PERMISSION_NOT_VERIFIED')
        self.assertEqual(self.state['successful_total'], 25)
        self.assertTrue(result['checkpoint'].is_dir())

    def test_later_resume_uses_new_witness_without_bootstrap_proof_replay(self):
        result = self.prepare('RESUME_RESTORE')
        self.assertIsNone(result['reason'])
        self.assertNotIn('bootstrap_evaluation_proof', self.events)
        self.assertEqual(self.state['last_evaluation_witness']['kind'], 'RESUME_RESTORE')

    def test_unbound_state_is_not_saved(self):
        with self.assertRaisesRegex(S.Hold, 'EXECUTION_EVALUATION_REQUIRED'):
            S.save_checkpoint(self.output, self.model, self.optimizer, self.scheduler, self.scaler,
                              self.state, self.lineage, self.torch)
        self.assertEqual(list(self.output.iterdir()), [])


class RetentionAndSourceTests(unittest.TestCase):
    def fixture(self, root):
        output = root / 'lora/qwen35_9b/fixture'; output.mkdir(parents=True)
        lineage = {'fixture': 'immutable-origin'}; rows = []; paths = {}
        for number in (5, 6, 25, 30, 35):
            name = f'checkpoint-u{number:08d}-a{number:08d}-g{number:020d}'
            path = output / name; path.mkdir(); payload = path / 'owned.bin'; payload.write_bytes(bytes([number]))
            record = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': name,
                      'lineage_sha256': S.canonical_sha(lineage), 'files_sha256': {'owned.bin': S.sha256_file(payload)}}
            S.atomic_json(path / 'checkpoint_manifest.json', record)
            row = {'directory': name, 'manifest_sha256': S.sha256_file(path / 'checkpoint_manifest.json'),
                   'successful_total': number, 'attempted_total': number,
                   'evaluated_at_current_step': True, 'holdout_loss': 2.0 - number / 100, 'retained': True}
            rows.append(row); paths[number] = path
        S.atomic_json(output / 'owner_checkpoints.json', {'schema': 'NOX_QWEN_OWNED_CHECKPOINTS_V1',
                      'lineage_sha256': S.canonical_sha(lineage), 'checkpoints': rows})
        S.atomic_json(output / 'latest_checkpoint.json', {k: rows[-1][k] for k in ('directory', 'manifest_sha256')})
        # Current mutable acceptance intentionally refers to35; historical6 must survive independently.
        current = {'checkpoint': str(paths[35]), 'checkpoint_manifest_sha256': rows[-1]['manifest_sha256']}
        S.atomic_json(output / 'owner_acceptance.json', current)
        ctx = {'execution': {'descriptor': {'anchor': {k: rows[2][k] for k in ('directory', 'manifest_sha256')}}},
               'certificate': {'checkpoint': str(paths[6]), 'checkpoint_manifest_sha256': rows[1]['manifest_sha256']}}
        return output, lineage, ctx, paths

    def test_original25_and_accepted6_survive_latest35_and_replaced_current_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output, lineage, ctx, paths = self.fixture(root)
            with patch.object(S, 'ROOT', root), patch.object(S, 'EXECUTION_CONTEXT', ctx), patch.object(S, 'verify_proof'):
                result = S.prune_checkpoints(output, lineage)
            self.assertFalse(paths[5].exists())
            self.assertTrue(all(paths[n].is_dir() for n in (6, 25, 30, 35)))
            self.assertEqual(result['deleted_verified_own_checkpoints'], 1)

    def test_changed_anchor_holds_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output, lineage, ctx, paths = self.fixture(root)
            (paths[25] / 'checkpoint_manifest.json').write_bytes(b'changed')
            with patch.object(S, 'ROOT', root), patch.object(S, 'EXECUTION_CONTEXT', ctx), patch.object(S, 'verify_proof'):
                with self.assertRaisesRegex(S.Hold, 'MIGRATION_ANCHOR'):
                    S.prune_checkpoints(output, lineage)
            self.assertTrue(all(path.is_dir() for path in paths.values()))

    def test_original_full_optimizer_scaler_scheduler_rng_loader_is_unchanged(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),
                         '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0')
        trees = [ast.parse(path.read_text()) for path in (ORIGINAL, HERE / 'qwen_student_training_entry_revision.py')]
        loaders = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'load_checkpoint')
                   for tree in trees]
        self.assertEqual(ast.dump(loaders[0]), ast.dump(loaders[1]))


if __name__ == '__main__':
    unittest.main()
