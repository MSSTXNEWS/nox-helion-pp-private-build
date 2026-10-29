"""G1-C R18 additional isolated negative checks; not committed to product source."""
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'Packages' / 'P04'
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('preflight_for_negative_checks',ROOT/'preflight_local_gpu.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
VALID='GPU-12345678-1234-1234-1234-123456789012'

class IsolatedCudaSafety(unittest.TestCase):
    def test_rejects_invalid_uuid_before_child(self):
        with patch.object(probe.subprocess,'run',side_effect=AssertionError('child must not spawn')):
            with self.assertRaisesRegex(RuntimeError,'GPU_UUID_INVALID'):
                probe._run_cuda_probe_isolated('gpu0')
    def test_refuses_parent_gpu_visibility_mismatch(self):
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'GPU-ffffffff-ffff-ffff-ffff-ffffffffffff'},clear=False):
            with patch.object(probe.subprocess,'run',side_effect=AssertionError('child must not spawn')):
                with self.assertRaisesRegex(RuntimeError,'CUDA_PARENT_VISIBLE_DEVICES_CONFLICT'):
                    probe._run_cuda_probe_isolated(VALID)
    def test_refuses_parent_device_order_mismatch(self):
        with patch.dict(os.environ,{'CUDA_DEVICE_ORDER':'FASTEST_FIRST'},clear=False):
            with patch.object(probe.subprocess,'run',side_effect=AssertionError('child must not spawn')):
                with self.assertRaisesRegex(RuntimeError,'CUDA_PARENT_DEVICE_ORDER_CONFLICT'):
                    probe._run_cuda_probe_isolated(VALID)
    def test_child_timeout_fails_closed(self):
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':VALID,'CUDA_DEVICE_ORDER':'PCI_BUS_ID'},clear=False):
            with patch.object(probe.subprocess,'run',side_effect=subprocess.TimeoutExpired('python',20)):
                with self.assertRaisesRegex(RuntimeError,'TORCH_CUDA_ISOLATED_PROCESS_FAILED'):
                    probe._run_cuda_probe_isolated(VALID)
    def test_unknown_child_fields_fail_closed(self):
        response=SimpleNamespace(returncode=0,stdout='{"cuda_runtime":"12.1","cuda_device_count":1,"trick":true}')
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':VALID,'CUDA_DEVICE_ORDER':'PCI_BUS_ID'},clear=False):
            with patch.object(probe.subprocess,'run',return_value=response):
                with self.assertRaisesRegex(RuntimeError,'TORCH_CUDA_ISOLATED_RESPONSE_INVALID'):
                    probe._run_cuda_probe_isolated(VALID)
    def test_parent_environment_unchanged_and_child_isolated(self):
        captured={}
        def fake_run(cmd,**kw):
            captured.update({'cmd':cmd,'env':kw['env'],'shell':kw.get('shell'),'timeout':kw['timeout'],'stdin':kw['stdin']})
            return SimpleNamespace(returncode=0,stdout='{"cuda_runtime":"12.1","cuda_device_count":1}')
        with patch.dict(os.environ,{},clear=True):
            with patch.object(probe.subprocess,'run',side_effect=fake_run):
                self.assertEqual(probe._run_cuda_probe_isolated(VALID)['cuda_device_count'],1)
            self.assertNotIn('CUDA_VISIBLE_DEVICES',os.environ)
            self.assertNotIn('CUDA_DEVICE_ORDER',os.environ)
        self.assertEqual(captured['cmd'][1],'-I')
        self.assertEqual(captured['env']['CUDA_VISIBLE_DEVICES'],VALID)
        self.assertEqual(captured['timeout'],20)
        self.assertIs(captured['stdin'],subprocess.DEVNULL)
    def test_cuda_child_refuses_bool_device_count(self):
        response=SimpleNamespace(returncode=0,stdout='{"cuda_runtime":"12.1","cuda_device_count":true}')
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':VALID,'CUDA_DEVICE_ORDER':'PCI_BUS_ID'},clear=False):
            with patch.object(probe.subprocess,'run',return_value=response):
                with self.assertRaisesRegex(RuntimeError,'TORCH_CUDA_ISOLATED_RESPONSE_INVALID'):
                    probe._run_cuda_probe_isolated(VALID)

if __name__=='__main__':unittest.main()
