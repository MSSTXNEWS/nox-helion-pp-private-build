"""Timing-only source deltas and exact deployment aliases; no native actions."""
import ast
import base64
import copy
import hashlib
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
OLD_STUDENT = '8291638636bb03f701802c634cf8b30d077a5176c33d3658fb5cb1c92d50f235'
OLD_ISSUER = '4be67c1d30d9513c96a3164c02e70056c47004922bbd3398cbc5e463f820f25d'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name, raw=None):
    value = types.ModuleType('_budget_fixture_' + name.removesuffix('.py'))
    value.__file__ = str(HERE / name)
    exec(compile((HERE / name).read_bytes() if raw is None else raw, value.__file__, 'exec'), value.__dict__)
    return value


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.entry = load('owner_qwen_transport_budget_entry.py')
        self.original = load('owner_qwen_revision_install.py')
        names = set(self.original.CANDIDATES) | set(self.original.UTILITIES) | {
            self.entry.CANONICAL_ISSUER, self.entry.CANDIDATE_ISSUER, self.entry.CANDIDATE_STUDENT}
        self.bundle = {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in names}
        self.entry.BUNDLE = dict(self.bundle)

    def test_student_only_changes_cooperative_staging_budget(self):
        old = (HERE / 'qwen_student_training_entry_transport_candidate.py').read_bytes()
        new = (HERE / self.entry.CANDIDATE_STUDENT).read_bytes()
        self.assertEqual(digest(old), OLD_STUDENT)
        self.assertEqual(new.count(b'STAGING_SECONDS = 2400.0'), 1)
        self.assertEqual(new.replace(b'STAGING_SECONDS = 2400.0', b'STAGING_SECONDS = 1200.0', 1), old)
        self.assertEqual(digest(new), self.entry.CANDIDATE_STUDENT_SHA)

    def test_issuer_only_changes_actual_student_pin_and_new_descriptor_ttl(self):
        old = (HERE / 'owner_qwen_transport_revision_install.py').read_bytes()
        new = (HERE / self.entry.CANDIDATE_ISSUER).read_bytes()
        self.assertEqual(digest(old), OLD_ISSUER)
        self.assertEqual(new.count(b"'expires_at': now + 3600"), 1)
        inverse = new.replace(self.entry.CANDIDATE_STUDENT_SHA.encode(), OLD_STUDENT.encode(), 1)
        inverse = inverse.replace(b"'expires_at': now + 3600", b"'expires_at': now + 1800", 1)
        self.assertEqual(inverse, old)
        self.assertEqual(digest(new), self.entry.CANDIDATE_ISSUER_SHA)

    def test_remaining_budget_keeps_io30_and_expires_at2400(self):
        tree = ast.parse((HERE / self.entry.CANDIDATE_STUDENT).read_bytes())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PublicTransportRevision')
        clock = types.SimpleNamespace(monotonic=lambda: 1201.0)
        scope = {'SealedModel': object, 'Hold': RuntimeError, 'time': clock}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<budget-class-only>', 'exec'), scope)
        model = scope['PublicTransportRevision']()
        self.assertEqual(model.STAGING_SECONDS, 2400.0)
        self.assertEqual(model.IO_SECONDS, 30.0); self.assertEqual(model.MAX_ATTEMPTS, 6)
        model._transport_deadline = model.STAGING_SECONDS
        self.assertEqual(model._remaining(), 30)
        clock.monotonic = lambda: 2399.5
        self.assertEqual(model._remaining(), 0.5)
        clock.monotonic = lambda: 2400.0
        with self.assertRaisesRegex(RuntimeError, '^HOLD_MEMFD_TRANSPORT_DEADLINE$'):
            model._remaining()

    def test_native_assets_use_new_bytes_only_at_existing_canonical_names(self):
        issuer = self.entry.bound_installer(); assets = issuer.assets()
        self.assertEqual(len(self.bundle), 14)
        self.assertEqual(issuer.__file__, '/root/nox/scripts/owner_qwen_revision_install.py')
        self.assertEqual(digest(assets[self.entry.CANONICAL_ISSUER]), self.entry.CANDIDATE_ISSUER_SHA)
        self.assertEqual(digest(assets[self.entry.CANONICAL_STUDENT]), self.entry.CANDIDATE_STUDENT_SHA)
        self.assertNotIn(self.entry.CANDIDATE_ISSUER, assets)
        self.assertNotIn(self.entry.CANDIDATE_STUDENT, assets)
        for name, native in self.original.CANDIDATES.items():
            if name != self.entry.CANONICAL_STUDENT:
                self.assertEqual(assets[native], (HERE / name).read_bytes())
        for name in self.original.UTILITIES:
            self.assertEqual(assets[name], (HERE / name).read_bytes())
        self.assertEqual(self.entry.BUNDLE, self.bundle)

    def test_extra_issuer_change_cannot_hide_behind_outer_pin(self):
        raw = (HERE / self.entry.CANDIDATE_ISSUER).read_bytes() + b'\n# unexpected modification\n'
        self.entry.BUNDLE[self.entry.CANDIDATE_ISSUER] = base64.b64encode(raw).decode()
        with patch.object(self.entry, 'CANDIDATE_ISSUER_SHA', digest(raw)):
            with self.assertRaisesRegex(RuntimeError, 'ISSUER_ONLY_BUDGET_AND_STUDENT_PIN_DELTA'):
                self.entry.bound_installer()

    def test_missing_or_changed_reviewed_source_fails_before_exec(self):
        for name in (self.entry.CANONICAL_ISSUER, self.entry.CANONICAL_STUDENT,
                     self.entry.CANDIDATE_ISSUER, self.entry.CANDIDATE_STUDENT):
            self.entry.BUNDLE = dict(self.bundle)
            self.entry.BUNDLE[name] = base64.b64encode(b'foreign').decode()
            with patch('builtins.exec', side_effect=AssertionError('must not execute')):
                with self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
                    self.entry.bound_installer()
        self.entry.BUNDLE = dict(self.bundle); self.entry.BUNDLE.pop(self.entry.CANONICAL_STUDENT)
        with self.assertRaisesRegex(RuntimeError, 'BUNDLE_SCOPE'):
            self.entry.bound_installer()

    def test_existing_shared_validator_accepts3600_but_no_larger_ttl(self):
        shared = load('owner_qwen_execution_revision.py')
        self.assertEqual(digest((HERE / shared.SELF).read_bytes()),
                         '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e')
        row = {'schema': shared.DESCRIPTOR_SCHEMA, 'request': '123', 'source_sha': 'a' * 40,
            'created_at': 1000.0, 'origin': copy.deepcopy(shared.ORIGIN), 'anchor': copy.deepcopy(shared.ANCHOR),
            'scheduler': dict(shared.SCHEDULER), 'runtime_sources': {
                shared.ENTRY: self.entry.CANDIDATE_STUDENT_SHA, shared.SELF: '1' * 64},
            'consumer_sources': {name: '2' * 64 for name in shared.CONSUMERS},
            'activation_issuer_sha256': self.entry.CANDIDATE_ISSUER_SHA,
            'bootstrap': {'expires_at': 4600.0, 'hold_sha256': shared.OLD_HOLD_SHA, 'pause_sha256': shared.OLD_PAUSE_SHA}}
        self.assertEqual(shared.descriptor(row), row)
        row['bootstrap']['expires_at'] = 4600.1
        with self.assertRaisesRegex(shared.Hold, 'BOOTSTRAP_SCOPE'):
            shared.descriptor(row)

    def test_observer_and_finalizer_have_only_exact_pin_changes_and_stay_unbound(self):
        old = (HERE / 'owner_qwen_transport_observe.py').read_bytes()
        new = (HERE / 'owner_qwen_transport_budget_observe.py').read_bytes()
        self.assertEqual(new.replace(self.entry.CANDIDATE_ISSUER_SHA.encode(), OLD_ISSUER.encode(), 1), old)
        old = (HERE / 'owner_qwen_transport_finalize.py').read_bytes()
        new = (HERE / 'owner_qwen_transport_budget_finalize.py').read_bytes()
        inverse = new.replace(self.entry.CANDIDATE_ISSUER_SHA.encode(), OLD_ISSUER.encode(), 1)
        self.assertEqual(inverse.replace(self.entry.CANDIDATE_STUDENT_SHA.encode(), OLD_STUDENT.encode(), 1), old)
        final = load('owner_qwen_transport_budget_finalize.py')
        self.assertIsNone(final.REFERENCE)
        with patch.object(final, 'load_installer', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(RuntimeError, 'EXPLICIT_IMMUTABLE_REFERENCE_REQUIRED'):
                final.main()

    def test_global_operator_substitution_keeps_the_private_alias_closure(self):
        raw = (HERE / 'owner_qwen_transport_budget_entry.py').read_bytes()
        token = b'__NOX_' + b'BUNDLE_JSON__'; self.assertEqual(raw.count(token), 1)
        expanded = raw.replace(token, repr(self.bundle).encode(), 1)
        entry = load('owner_qwen_transport_budget_entry.py', expanded)
        assets = entry.bound_installer().assets()
        self.assertEqual(digest(assets[entry.CANONICAL_ISSUER]), entry.CANDIDATE_ISSUER_SHA)
        self.assertEqual(digest(assets[entry.CANONICAL_STUDENT]), entry.CANDIDATE_STUDENT_SHA)


if __name__ == '__main__':
    unittest.main()
