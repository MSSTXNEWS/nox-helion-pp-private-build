"""Explicit-ref and source binding tests without invoking native finalization."""
import hashlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).parent
RAW = (HERE / 'owner_qwen_transport_finalize.py').read_bytes()


def module(raw=RAW):
    value = types.ModuleType('_test_transport_finalize')
    exec(compile(raw, str(HERE / 'owner_qwen_transport_finalize.py'), 'exec'), value.__dict__)
    return value


# Synthetic fixture, never written into the production template or native state.
REF = {'request': '123', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}


class FinalizerTests(unittest.TestCase):
    def test_unbound_template_holds_before_any_native_read(self):
        entry = module()
        self.assertIsNone(entry.REFERENCE)
        with mock.patch.object(entry, 'load_installer', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(RuntimeError, 'EXPLICIT_IMMUTABLE_REFERENCE_REQUIRED'):
                entry.main()

    def test_malformed_or_partial_reference_holds_before_any_native_read(self):
        entry = module()
        with mock.patch.object(entry, 'load_installer', side_effect=AssertionError('must not read')):
            for ref in (None, {}, {**REF, 'request': 123}, {**REF, 'receipt_sha256': None}, {**REF, 'extra': True}):
                with self.subTest(ref=ref), self.assertRaisesRegex(RuntimeError, 'EXPLICIT_IMMUTABLE_REFERENCE_REQUIRED'):
                    entry.bound_installer(ref)

    def test_one_literal_render_calls_only_existing_finalize_once(self):
        anchor = b'REFERENCE = None\n'
        self.assertEqual(RAW.count(anchor), 1)
        rendered = RAW.replace(anchor, b'REFERENCE = ' + repr(REF).encode() + b'\n', 1)
        entry = module(rendered)
        core = types.SimpleNamespace(finalize_current=mock.Mock(return_value=2), main=mock.Mock(side_effect=AssertionError('no install')))
        with mock.patch.object(entry, 'bound_installer', return_value=core) as binding, \
                mock.patch.object(entry, 'pending_context') as pending:
            self.assertEqual(entry.main(), 2)
        binding.assert_called_once_with(REF); core.finalize_current.assert_called_once_with(); core.main.assert_not_called()
        pending.assert_called_once_with(core)

    def test_actual_candidate_installer_loads_definitions_without_running(self):
        entry = module()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'owner_qwen_revision_install.py'
            raw = (HERE / 'owner_qwen_transport_revision_install.py').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry.PIN)
            path.write_bytes(raw); path.chmod(0o600)
            with mock.patch.object(entry, 'PATH', path):
                core = entry.load_installer()
            self.assertEqual(core.PINS[core.STUDENT], entry.STUDENT_PIN)
            self.assertEqual(core.__file__, str(path))
            self.assertEqual(core.BUNDLE, {})

    def test_old_installer_or_symlink_fails(self):
        entry = module()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'owner_qwen_revision_install.py'
            path.write_bytes((HERE / 'owner_qwen_revision_install.py').read_bytes()); path.chmod(0o600)
            with mock.patch.object(entry, 'PATH', path), self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
                entry.load_installer()
            alias = Path(folder) / 'alias.py'; alias.symlink_to(path)
            with mock.patch.object(entry, 'PATH', alias), self.assertRaisesRegex(RuntimeError, 'SOURCE_PATH'):
                entry.load_installer()

    def test_finalizer_shared_context_is_explicit_and_cannot_switch_reference(self):
        entry = module()
        ctx = {'context': dict(REF), 'execution': {'runtime_entry_sha256': entry.STUDENT_PIN,
               'verifier_sha256': entry.SHARED_PIN, 'descriptor': {'activation_issuer_sha256': entry.PIN}}}
        actual = mock.Mock(return_value=ctx)
        shared = types.SimpleNamespace(current_context=actual)
        loader = mock.Mock(return_value=shared)
        core = types.SimpleNamespace(module=loader)
        with mock.patch.object(entry, 'load_installer', return_value=core):
            bound = entry.bound_installer(REF)
        raw = (HERE / entry.SHARED).read_bytes()
        loaded = bound.module(entry.SHARED, raw)
        self.assertEqual(loaded.current_context(), ctx)
        actual.assert_called_once_with(REF)
        with self.assertRaisesRegex(RuntimeError, 'REFERENCE_ARGUMENT_CHANGED'):
            loaded.current_context({**REF, 'request': '456'})
        ctx['context'] = {**REF, 'request': '456'}
        with self.assertRaisesRegex(RuntimeError, 'CURRENT_EXECUTION_BINDING'):
            loaded.current_context()

    def test_bad_shared_bytes_fail_before_execution_other_modules_keep_original_loader(self):
        entry = module(); loader = mock.Mock(return_value=object())
        core = types.SimpleNamespace(module=loader)
        with mock.patch.object(entry, 'load_installer', return_value=core):
            bound = entry.bound_installer(REF)
        with self.assertRaisesRegex(RuntimeError, 'SHARED_PIN'):
            bound.module(entry.SHARED, b'foreign')
        loader.assert_not_called()
        bound.module('owner_qwen_training_guard.py', b'guard passed through')
        loader.assert_called_once_with('owner_qwen_training_guard.py', b'guard passed through')

    def test_already_activated_or_expired_never_enters_frozen_mutation_handler(self):
        entry = module()
        ctx = {'context': dict(REF)}
        shared = types.SimpleNamespace(current_context=mock.Mock(return_value=ctx), activation_status=mock.Mock())
        core = types.SimpleNamespace(SCRIPTS=Path('/unused'), read=mock.Mock(return_value=b'pinned shared'),
                                     module=mock.Mock(return_value=shared), finalize_current=mock.Mock())
        for state in ({'active': True, 'bootstrap_pending': False},
                      {'active': False, 'bootstrap_pending': False}, {'active': 0, 'bootstrap_pending': 1}):
            shared.activation_status.return_value = state
            with mock.patch.object(entry, 'bound_installer', return_value=core), \
                    self.assertRaisesRegex(RuntimeError, 'NOT_PENDING_USE_READ_ONLY_OBSERVER'):
                entry.main(REF)
        core.finalize_current.assert_not_called()
        shared.activation_status.return_value = {'active': False, 'bootstrap_pending': True}
        self.assertEqual(entry.pending_context(core), ctx)


if __name__ == '__main__':
    unittest.main()
