"""Exact inactive installation inputs, reversible scope and lease behavior."""
import base64
from contextlib import redirect_stdout
import fcntl
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


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


M = load(HERE / 'owner_qwen_guard_install_entry.py', 'inactive_qwen_guard_test')
G = load(HERE / 'owner_qwen_training_guard.py', 'inactive_qwen_guard_source_test')


def assets():
    paths = {name: HERE / name for name in M.PINS}
    paths.update({'owner_qwen_window_entry.py': Path('/tmp/nox_qwen_window_entry_4d5.py'),
        'owner_qwen_install_entry.py': Path('/tmp/nox_qwen_owner_qwen_install_entry.py'),
        'owner_subagent_install_entry.py': Path('/tmp/nox_subagent_review_b022334/owner_subagent_install_entry.py')})
    return {name: base64.b64encode(path.read_bytes()).decode() for name, path in paths.items()}


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundled = assets()
        with patch.object(M, 'BUNDLE', cls.bundled):
            cls.assets = M.bundle()
            cls.base, cls.fresh, cls.h, cls.recovery = M.helpers(cls.assets)

    def test_exact_twelve_file_closure_imports_definitions_without_main(self):
        self.assertEqual(len(self.assets), 12)
        self.assertEqual(self.h.SERVICE, 'nox-dispatcher-t855u')
        self.assertEqual(self.base.WINDOW_CONTEXT['receipt_sha256'], '4547158a490e9c367a6f59f0936f6c0ae3836d40a797fe47b1f303dae38f4308')
        self.assertEqual(self.base.FRESH_CONTEXT['receipt_sha256'], '5e39c36179c1d177fe5984fdddfb46ba5264c3975631c3137e1a612ed3e58d73')
        for name in ('read', 'atomic', 'service', 'process', 'global_stop', 'queue_state', 'health', 'active_model'):
            self.assertTrue(callable(getattr(self.h, name)))
        self.assertTrue(callable(self.base.rollback_controller_plan))
        altered = dict(self.bundled, **{M.GUARD: base64.b64encode(b'raise RuntimeError("must not execute")').decode()})
        with patch.object(M, 'BUNDLE', altered), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            M.bundle()

    def native_dispatcher(self):
        raw = Path('/tmp/nox_native_sources/nox_dispatcher_admitted_a409.py').read_bytes()
        anchor = b'if __name__ == "__main__":\n    main()'
        raw = raw.replace(anchor, b'# NOX_NATIVE_SUBAGENTS_BIND_V1\nimport owner_subagent_dispatcher\nowner_subagent_dispatcher.bind_dispatcher(globals())\n\n' + anchor)
        return self.base.patch_dispatcher(raw)

    def test_exact_existing_dispatcher_preserved_outside_two_bindings(self):
        before = self.native_dispatcher(); after = M.patch_dispatcher(before, self.base)
        self.assertEqual(M.digest(before), M.DISPATCHER_BEFORE)
        self.assertEqual(M.digest(after), '439f669487e965b3a9709078674c1fbff6ceff332b0ad2089dad1f218c2e57cf')
        self.assertEqual(after.replace(M.BINDING.encode(), b'', 1), before)
        self.assertLess(after.index(self.base.MARKER.encode()), after.index(M.MARKER.encode()))
        self.assertLess(after.index(b'# NOX_QWEN_MEDIA_GUARD_BIND_V1'), after.index(b'# NOX_OWNER_TASK_LIFECYCLE_BIND_V1'))
        with self.assertRaisesRegex(RuntimeError, 'DISPATCHER_PREIMAGE'):
            M.patch_dispatcher(after, self.base)
        with self.assertRaisesRegex(RuntimeError, 'DISPATCHER_PREIMAGE'):
            M.patch_dispatcher(before + b'\n# foreign change\n', self.base)

    def test_disabled_configuration_is_exact_and_has_no_1000_context(self):
        value = G.configuration(None, M.GUARD_SHA, enabled=False)
        raw = M.encoded(value)
        self.assertEqual(M.digest(raw), '9335aac28edf0c60389ac6976ae599009ddb83a22a61b0c1b112557f0a30e423')
        self.assertEqual(len(raw), 894)
        self.assertIs(value['enabled'], False); self.assertIsNone(value['window_admission'])

    def test_actual_prior_receipt_is_raw_hash_bound_and_existing_configs_are_protected(self):
        raw = Path('/tmp/nox_qwen_media_install_native_exact_6907909296.json').read_bytes()
        self.assertEqual(M.digest(raw), M.PRIOR['receipt_sha256'])
        # Use the exact config serialization from the already accepted installer.
        prior_config = self.base.encoded(self.base.configuration(self.base.WINDOW_CONTEXT, M.MEDIA_CONFIG_SHA))
        media_config = b'public fixture for media configuration'
        mapping = {M.STATE / ('owner_qwen_media_handoff_' + M.PRIOR['request'] + '.json'): raw,
                   self.base.CONFIG: prior_config, M.ROOT / 'config/owner_media_runtime.json': media_config}
        mapping.update({M.SCRIPTS / name: self.assets[name] for name in {self.base.ADAPTER, *self.base.DEPS}})
        h = types.SimpleNamespace(read=lambda path, maximum=None: mapping[path])
        base = types.SimpleNamespace(**{name: getattr(self.base, name) for name in
             ('WINDOW_CONTEXT', 'FRESH_CONTEXT', 'ADAPTER', 'ADAPTER_SHA', 'DEPS', 'CONFIG')}, check_fresh=Mock())
        with patch.object(M, 'MEDIA_CONFIG_SHA', M.digest(media_config)):
            # A different actual main media config cannot use the old sealed receipt.
            with self.assertRaisesRegex(RuntimeError, 'PRIOR_RECEIPT_SCOPE'):
                M.prior_proof(h, base, self.fresh, M.DISPATCHER_BEFORE)
        mapping[next(key for key in mapping if key.name.startswith('owner_qwen_media_handoff_'))] = raw + b' '
        with self.assertRaisesRegex(RuntimeError, 'PRIOR_RECEIPT_SHA'):
            M.prior_proof(h, base, self.fresh, M.DISPATCHER_BEFORE)

    def test_existing_leases_are_nonblocking_and_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'existing.lock'; path.write_bytes(b'')
            fd = M.acquire(self.h, path)
            try:
                with self.assertRaises(BlockingIOError):
                    M.acquire(self.h, path)
            finally:
                os.close(fd)
            with self.assertRaises(FileNotFoundError):
                M.acquire(self.h, Path(folder) / 'missing.lock')
            target = Path(folder) / 'symlink'; target.symlink_to(path)
            with self.assertRaisesRegex(RuntimeError, 'PATH_OR_SYMLINK'):
                M.acquire(self.h, target)

    def test_timeout_rollback_uses_reviewed_settled_state_plan(self):
        for state in ('STOPPING', 'STARTING', 'UNKNOWN'):
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'ROLLBACK_CONTROLLER_UNSETTLED'):
                self.base.rollback_controller_plan(state, False)
        self.assertEqual(self.base.rollback_controller_plan('STOPPED', False), {'stop_first': False, 'restart': True})
        self.assertEqual(self.base.rollback_controller_plan('RUNNING', True), {'stop_first': True, 'restart': True})

    def test_child_smoke_is_compilable_bounded_and_stderr_stays_private(self):
        compile(M.SMOKE, '<guard-smoke>', 'exec')
        response = types.SimpleNamespace(returncode=2,
            stdout=b'{"state":"HOLD_QWEN_INACTIVE_GUARD_SMOKE","exception_class":"AssertionError"}',
            stderr=b'PRIVATE_FIXTURE')
        output = io.StringIO()
        with patch.object(M.subprocess, 'run', return_value=response) as run, redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, 'SMOKE_FAILED'):
                M.smoke('/usr/bin/python3')
        self.assertNotIn('PRIVATE_FIXTURE', output.getvalue())
        self.assertEqual(run.call_args.args[0][:3], ['/usr/bin/python3', '-I', '-B'])
        self.assertEqual(run.call_args.kwargs['timeout'], 45)


if __name__ == '__main__':
    unittest.main()
