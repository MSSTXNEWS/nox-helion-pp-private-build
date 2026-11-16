#!/usr/bin/env python3
"""V13-04 offline regression: trusted virtualenv Python vs unsafe symlink.

No OneHost access, no TRL/torch import, no CUDA context or trainer.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('nox_v13_native_inspect', HERE / 'owner_native_inspect.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PinnedInterpreterAdmissionTests(unittest.TestCase):
    def make_venv(self, root):
        root.mkdir()
        (root / 'bin').mkdir()
        (root / 'pyvenv.cfg').write_text('home = /usr/bin\n')
        executable = root / 'bin' / 'python3.12'
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        (root / 'bin' / 'python').symlink_to('python3.12')
        return root / 'bin' / 'python'

    def admit(self, path, root):
        return module.pinned_python_path_status(
            path, venv_root=root, trusted_uid=os.getuid(),
            system_dirs=(Path('/usr/bin'), Path('/usr/local/bin')))

    def test_root_owned_venv_local_symlink_is_not_false_missing(self):
        with tempfile.TemporaryDirectory() as d:
            py = self.make_venv(Path(d) / 'venv')
            self.assertEqual(self.admit(py, py.parent.parent),
                             'PINNED_NATIVE_PYTHON_TRUSTED')

    def test_regular_venv_python_is_accepted_without_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            py = self.make_venv(Path(d) / 'venv')
            py.unlink()
            py.write_text('#!/bin/sh\nexit 0\n')
            py.chmod(0o755)
            self.assertEqual(self.admit(py, py.parent.parent),
                             'PINNED_NATIVE_PYTHON_TRUSTED')

    def test_symlink_escape_to_unapproved_directory_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            py=self.make_venv(root/'venv')
            outside=root/'outside'
            outside.mkdir()
            rogue=outside/'python3.12'
            rogue.write_text('#!/bin/sh\nexit 0\n')
            rogue.chmod(0o755)
            py.unlink()
            py.symlink_to(rogue)
            self.assertEqual(self.admit(py, root/'venv'),
                             'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED')

    def test_writable_venv_directory_or_symlinked_config_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            py=self.make_venv(root/'venv')
            (root/'venv'/'bin').chmod(0o777)
            self.assertEqual(self.admit(py, root/'venv'),
                             'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED')
            (root/'venv'/'bin').chmod(0o755)
            cfg=root/'venv'/'pyvenv.cfg'
            cfg.unlink()
            cfg.symlink_to(root/'other-config')
            (root/'other-config').write_text('home = /usr/bin')
            self.assertEqual(self.admit(py, root/'venv'),
                             'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED')

    def test_broken_symlink_and_wrong_path_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            py=self.make_venv(root/'venv')
            (root/'venv'/'bin'/'python3.12').unlink()
            self.assertEqual(self.admit(py, root/'venv'),
                             'HOLD_PINNED_NATIVE_PYTHON_MISSING')
            self.assertEqual(self.admit(root/'rogue', root/'venv'),
                             'HOLD_PINNED_NATIVE_PYTHON_PATH')

    def test_probe_does_not_launch_unvetted_interpreter(self):
        with mock.patch.object(module, 'pinned_python_path_status',
                               return_value='HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'), \
             mock.patch.object(module, 'run') as launch:
            result=module.pinned_sftconfig_signature_probe(Path('/root/venv_volta/bin/python'))
        self.assertEqual(result['status'], 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED')
        self.assertIs(result['constructor_executed'], False)
        launch.assert_not_called()

    def test_trusted_path_probe_uses_venv_identity_and_no_trainer(self):
        signature = ('NOX_SFTCONFIG_SIGNATURE='
                     '{"schema":"NOX_SFTCONFIG_NATIVE_SIGNATURE_V1",'
                     '"trl_version":"1.18.0","missing_required_kwargs":[],'
                     '"save_safetensors_parameter":false}')
        with mock.patch.object(module, 'pinned_python_path_status',
                               return_value='PINNED_NATIVE_PYTHON_TRUSTED'), \
             mock.patch.object(module, 'run', return_value=(0, signature)) as launch:
            result=module.pinned_sftconfig_signature_probe(Path('/root/venv_volta/bin/python'))
        self.assertEqual(result['status'], 'LEGACY_TRUE_REQUIRES_SAFE_OMISSION')
        self.assertIs(result['constructor_executed'], False)
        args, kwargs = launch.call_args
        self.assertEqual(args[0][:3], ['/root/venv_volta/bin/python', '-I', '-c'])
        self.assertIn("sys.version_info[:2] != (3, 12)", args[0][3])
        self.assertIn("os.path.realpath(sys.prefix)", args[0][3])
        self.assertEqual(kwargs['timeout'], 30)


    def test_v14_package_metadata_untrusted_never_runs(self):
        with mock.patch.object(module, 'pinned_python_path_status',
                               return_value='HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'), \
             mock.patch.object(module, 'run') as execute:
            got = module.installed_package_versions_readback(
                Path('/root/venv_volta/bin/python'))
        self.assertEqual(got['status'], 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED')
        self.assertIsNone(got['rc'])
        self.assertEqual(got['versions'], {})
        execute.assert_not_called()

    def test_v14_package_metadata_trusted_uses_isolation_and_child_identity(self):
        import json
        names = ['torch','transformers','accelerate','datasets','safetensors',
                 'peft','bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py',
                 'sqlite-vec','playwright','pytest','ruff']
        payload = json.dumps({name: '1.2.3' for name in names})
        with mock.patch.object(module, 'pinned_python_path_status',
                               return_value='PINNED_NATIVE_PYTHON_TRUSTED'), \
             mock.patch.object(module, 'run', return_value=(0, payload)) as execute:
            got = module.installed_package_versions_readback(
                Path('/root/venv_volta/bin/python'))
        self.assertEqual(got['status'], 'READ_ONLY_VERSION_METADATA')
        self.assertEqual(got['versions']['torch'], '1.2.3')
        argv = execute.call_args.args[0]
        self.assertEqual(argv[:3], ['/root/venv_volta/bin/python', '-I', '-c'])
        self.assertIn("sys.version_info[:2] != (3, 12)", argv[3])
        self.assertIn("os.path.realpath(sys.prefix)", argv[3])
        self.assertIn("importlib.metadata", argv[3])
        self.assertNotIn('import torch', argv[3])
        self.assertEqual(execute.call_args.kwargs['timeout'], 20)
        self.assertFalse(got['cuda_context_created'])
        self.assertFalse(got['trainer_started'])

    def test_v14_package_metadata_failed_or_forged_output_holds(self):
        for rc, payload, state in (
            (1, '', 'HOLD_PACKAGE_METADATA_PROBE_FAILED'),
            (0, '{broken', 'HOLD_PACKAGE_METADATA_INVALID'),
            (0, '{}', 'HOLD_PACKAGE_METADATA_INVALID'),
            (0, '1', 'HOLD_PACKAGE_METADATA_INVALID'),
            (0, 'x' * 16385, 'HOLD_PACKAGE_METADATA_PROBE_FAILED'),
        ):
            with self.subTest(rc=rc, state=state), \
                 mock.patch.object(module, 'pinned_python_path_status',
                                   return_value='PINNED_NATIVE_PYTHON_TRUSTED'), \
                 mock.patch.object(module, 'run', return_value=(rc, payload)):
                got = module.installed_package_versions_readback(
                    Path('/root/venv_volta/bin/python'))
            self.assertEqual(got['status'], state)
            self.assertEqual(got['versions'], {})

    def test_v14_controls_reuses_pinned_probe_not_raw_python_exec(self):
        import inspect
        source = inspect.getsource(module.controls)
        self.assertIn('rows.append(installed_package_versions_readback(py))', source)
        self.assertNotIn("run([str(py),'-c',code],20)", source)



if __name__ == '__main__':
    unittest.main()
