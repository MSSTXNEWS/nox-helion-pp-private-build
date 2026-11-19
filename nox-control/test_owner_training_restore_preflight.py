import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import patch

import owner_training_restore_preflight as probe


def accepted():
    return {'schema':probe.SCHEMA,'state':probe.STATE,'hybrid_sha256':probe.HYBRID_SHA,
        'installed_source_sha256':{'trainer':'da5a792ffed97570b8d936f19b7090cbac4ff699b5e29b620a67ba1033d20c7d',
            'peft_model':'d22a1c50dea7a046ce28e71a79dfc20b1d96a2d238a9b457be6a88b6068e04d5',
            'peft_state':'eb764515dce074bc5b7655a90e945af906e924eb8305b1ec265fc79ca52a8438'},
        'checks':{key:True for key in ('real_safetensors_restore_verified','parameter_objects_preserved',
            'trainable_device_and_dtype_preserved','frozen_cpu_base_preserved','base_device_map_preserved',
            'optimizer_not_created','scheduler_and_scaler_sentinels_preserved','rng_state_preserved',
            'seven_synthetic_files_unchanged','restore_hook_positive_proof')},
        'trainable_tensors':2,'trainable_parameters':8,'peak_tensor_allocation_bytes':1024,
        'temporary_checkpoint_files':7,'synthetic_checkpoint_only':True,'real_checkpoint_read':False,
        'base_model_loaded':False,'training_step_performed':False,'optimizer_step_performed':False,
        'service_or_training_flags_changed':False,'private_tensor_or_source_content_exported':False,
        'temporary_directory_removed':True}


class PreflightTests(unittest.TestCase):
    def test_wrong_hybrid_never_starts_child(self):
        with patch.object(probe.subprocess,'run') as run,self.assertRaisesRegex(RuntimeError,'HYBRID_PIN'):
            probe.run_preflight(b'unreviewed')
        run.assert_not_called()

    def test_exact_source_cpu_guard_precedes_torch_and_toy_is_isolated(self):
        compile(probe.CHILD,'<toy-preflight>','exec')
        self.assertLess(probe.CHILD.index('pins=installed_sources()'),probe.CHILD.index('import torch'))
        self.assertIn("TemporaryDirectory(prefix='nox-restore-preflight-',dir='/dev/shm')",probe.CHILD)
        self.assertNotIn('native.load_model(',probe.CHILD)
        self.assertNotIn('torch.load(',probe.CHILD)
        self.assertNotIn('optimizer.step(',probe.CHILD)
        self.assertNotIn('supervisorctl',probe.CHILD)
        self.assertIn('module.OUTPUT=Path(directory)',probe.CHILD)
        self.assertIn('trainer._load_from_checkpoint(str(checkpoint))',probe.CHILD)
        self.assertIn("Path('/workspace/NOX_STOP')",probe.CHILD)

    def test_pinned_payload_gpu1_timeout_and_strict_result(self):
        raw=Path('hybrid_training_entry.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),probe.HYBRID_SHA)
        with patch.object(probe.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(accepted()).encode(),stderr=b'PRIVATE')) as run:
            value=probe.run_preflight(raw)
        self.assertEqual(value['trainable_parameters'],8)
        call=run.call_args
        self.assertEqual(call.kwargs['env']['CUDA_VISIBLE_DEVICES'],'1')
        self.assertEqual(call.kwargs['timeout'],50)
        self.assertEqual(call.args[0][:3],[probe.PYTHON,'-I','-B'])

    def test_extra_private_fields_and_failed_invariants_are_rejected(self):
        for mutate in (lambda v:v.update(private='SECRET'),
                       lambda v:v['checks'].update(parameter_objects_preserved=False),
                       lambda v:v.update(peak_tensor_allocation_bytes=2*1024**2),
                       lambda v:v['installed_source_sha256'].update(trainer='0'*64)):
            value=accepted();mutate(value)
            with self.assertRaisesRegex(RuntimeError,'HOLD_RESTORE_PREFLIGHT_RESULT'):
                probe.validate_result(value)

    def test_child_hold_exports_only_enum_and_no_stderr(self):
        raw=Path('hybrid_training_entry.py').read_bytes()
        value={'state':'HOLD_TINY_GPU_RESTORE_PREFLIGHT','stage':'INPLACE_RESTORE',
               'reason':'HOLD_ADAPTER_RESTORE_READBACK','raw_exception_exported':False}
        output=io.StringIO()
        with patch.object(probe.subprocess,'run',return_value=types.SimpleNamespace(returncode=2,stdout=json.dumps(value).encode(),stderr=b'PRIVATE')),contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'HOLD_ADAPTER_RESTORE_READBACK'):
                probe.run_preflight(raw)
        self.assertNotIn('PRIVATE',output.getvalue())
        value['reason']='SECRET /private/path'
        with patch.object(probe.subprocess,'run',return_value=types.SimpleNamespace(returncode=2,stdout=json.dumps(value).encode())),contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'FAILURE_SCHEMA'):
                probe.run_preflight(raw)

    def test_timeout_does_not_claim_restoration(self):
        raw=Path('hybrid_training_entry.py').read_bytes()
        with patch.object(probe.subprocess,'run',side_effect=subprocess.TimeoutExpired('private',50)),self.assertRaisesRegex(RuntimeError,'HOLD_RESTORE_PREFLIGHT_TIMEOUT'):
            probe.run_preflight(raw)


if __name__=='__main__':unittest.main()
