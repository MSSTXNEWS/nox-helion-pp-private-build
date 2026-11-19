import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('restore_test_hybrid', Path(__file__).with_name('hybrid_training_entry.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Tensor:
    def __init__(self, value, shape=(2, 2), device='cuda', dtype='float32', trainable=True):
        self.value, self.shape = value, shape
        self.device, self.dtype = types.SimpleNamespace(type=device), dtype
        self.requires_grad, self.grad = trainable, None
    def numel(self):
        return self.shape[0] * self.shape[1]
    def to(self, *, device, dtype):
        return Tensor(self.value, self.shape, device.type, dtype)
    def copy_(self, value):
        self.value = value.value


class Model:
    def __init__(self):
        self.params = {'base.weight': Tensor(99, device='cpu', trainable=False),
            'base.layer.lora_A.default.weight': Tensor(1), 'base.layer.lora_B.default.weight': Tensor(0)}
        self.active_adapters = ['default']
        self.peft_config = {'default': object()}
        self.hf_device_map = {'layer': 0, 'base': 'cpu'}
    def named_parameters(self):
        return iter(self.params.items())


def fake_tensor_sha(model, _):
    return m.json_sha({name: p.value for name, p in model.params.items() if p.requires_grad})


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name)
        self.cp = self.output / 'checkpoint-5'
        self.cp.mkdir()
        for name in ('optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'adapter_config.json', 'adapter_model.safetensors'):
            (self.cp / name).write_bytes(('verified ' + name).encode())
        (self.cp / 'trainer_state.json').write_text('{"global_step":5}')
        self.model = Model()
        self.trainer = types.SimpleNamespace(model=self.model, optimizer=None, lr_scheduler=object(), accelerator=object(), _load_from_checkpoint=mock.Mock())
        self.torch = types.SimpleNamespace(float32='float32', no_grad=contextlib.nullcontext,
            isfinite=lambda x: types.SimpleNamespace(all=lambda: types.SimpleNamespace(item=lambda: True)))
        self.values = {'base.layer.lora_A.weight': Tensor(7, device='cpu'), 'base.layer.lora_B.weight': Tensor(3, device='cpu')}
        self.lineage = {'native_sha256': 'a' * 64, 'targets': m.fp32_adapters(self.model, self.torch, convert=False)}
        restored = Model()
        restored.params['base.layer.lora_A.default.weight'].value = 7
        restored.params['base.layer.lora_B.default.weight'].value = 3
        self.receipt = {'schema': m.SCHEMA, 'native_sha256': 'a' * 64, 'lineage_sha256': m.json_sha(self.lineage), 'global_step': 5,
            'checkpoint': m.checkpoint_record(self.cp), 'after_tensor_sha256': fake_tensor_sha(restored, self.torch)}
        (self.output / 'owner_receipt_step_5.json').write_text(json.dumps(self.receipt))
        st = types.ModuleType('safetensors.torch')
        st.load_file = lambda *a, **kw: self.values
        self.patches = [mock.patch.object(m, 'OUTPUT', self.output), mock.patch.object(m, 'tensor_sha', fake_tensor_sha),
            mock.patch.dict(sys.modules, {'safetensors': types.ModuleType('safetensors'), 'safetensors.torch': st})]
        for patch in self.patches: patch.start()
    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()
        self.directory.cleanup()
    def bind(self):
        return m.bind_checkpoint_restore(self.trainer, self.cp, self.torch, self.lineage)

    def test_copy_preserves_parameters_base_and_external_state(self):
        identities = {name: id(p) for name, p in self.model.params.items()}
        old_method, scheduler, accelerator = self.trainer._load_from_checkpoint, self.trainer.lr_scheduler, self.trainer.accelerator
        before_files = m.checkpoint_record(self.cp)
        proof = self.bind()
        self.trainer._load_from_checkpoint(str(self.cp))
        self.assertTrue(proof['restored'])
        self.assertEqual(proof['trainable_tensors'], 2)
        self.assertEqual(fake_tensor_sha(self.model, self.torch), self.receipt['after_tensor_sha256'])
        self.assertEqual(identities, {name: id(p) for name, p in self.model.params.items()})
        self.assertEqual(self.model.params['base.weight'].value, 99)
        self.assertEqual(self.model.params['base.weight'].device.type, 'cpu')
        self.assertEqual(m.checkpoint_record(self.cp), before_files)
        self.assertIs(self.trainer.lr_scheduler, scheduler)
        self.assertIs(self.trainer.accelerator, accelerator)
        old_method.assert_not_called()

    def test_extra_checkpoint_tensor_rejected_before_any_copy(self):
        self.bind()
        self.values['base.weight'] = Tensor(100, device='cpu')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_KEYS'):
            self.trainer._load_from_checkpoint(str(self.cp))
        self.assertEqual(self.model.params['base.layer.lora_A.default.weight'].value, 1)

    def test_all_shapes_validated_before_any_copy(self):
        self.bind()
        self.values['base.layer.lora_B.weight'].shape = (2, 3)
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_TENSOR_SCHEMA'):
            self.trainer._load_from_checkpoint(str(self.cp))
        self.assertEqual(self.model.params['base.layer.lora_A.default.weight'].value, 1)

    def test_parameter_replacement_or_base_placement_change_rejected(self):
        self.bind()
        self.model.params['base.layer.lora_A.default.weight'] = Tensor(1)
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_PRELOAD_PLACEMENT_CHANGED'):
            self.trainer._load_from_checkpoint(str(self.cp))

    def test_restore_must_precede_optimizer_creation(self):
        self.bind()
        self.trainer.optimizer = object()
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_SCOPE_OR_ORDER'):
            self.trainer._load_from_checkpoint(str(self.cp))

    def test_checkpoint_change_is_rejected(self):
        self.bind()
        (self.cp / 'scaler.pt').write_bytes(b'reset')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_CHECKPOINT_CHANGED'):
            self.trainer._load_from_checkpoint(str(self.cp))

    def test_replaced_trainer_model_is_rejected(self):
        self.bind()
        self.trainer.model = Model()
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_SCOPE_OR_ORDER'):
            self.trainer._load_from_checkpoint(str(self.cp))

    def test_second_restore_is_rejected(self):
        self.bind()
        self.trainer._load_from_checkpoint(str(self.cp))
        with self.assertRaisesRegex(RuntimeError, 'HOLD_ADAPTER_RESTORE_SCOPE_OR_ORDER'):
            self.trainer._load_from_checkpoint(str(self.cp))


if __name__ == '__main__':
    unittest.main()
