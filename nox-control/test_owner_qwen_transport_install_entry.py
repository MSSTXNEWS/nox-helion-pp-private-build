"""Review the actual candidate aliases without invoking an installer action."""
import ast
import base64
import hashlib
from pathlib import Path
import types
import unittest
from unittest import mock


HERE = Path(__file__).parent


def load(name, raw=None):
    path = HERE / (name + '.py')
    module = types.ModuleType('_test_' + name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes() if raw is None else raw, str(path), 'exec'), module.__dict__)
    return module


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.entry = load('owner_qwen_transport_install_entry')
        self.original = load('owner_qwen_revision_install')
        names = set(self.original.CANDIDATES) | set(self.original.UTILITIES) | {
            self.entry.CANONICAL_ISSUER, self.entry.CANDIDATE_ISSUER,
            self.entry.CANDIDATE_STUDENT,
        }
        self.bundle = {name: b64((HERE / name).read_bytes()) for name in names}
        self.entry.BUNDLE = dict(self.bundle)

    def test_actual_assets_have_new_bytes_under_only_canonical_native_names(self):
        issuer = self.entry.bound_installer()
        prepared = issuer.assets()
        self.assertEqual(issuer.__file__, '/root/nox/scripts/' + self.entry.CANONICAL_ISSUER)
        self.assertEqual(sha(prepared[self.entry.CANONICAL_ISSUER]), self.entry.CANDIDATE_ISSUER_SHA)
        self.assertEqual(sha(prepared[self.entry.CANONICAL_STUDENT]), self.entry.CANDIDATE_STUDENT_SHA)
        expected_names = set(self.original.CANDIDATES.values()) | set(self.original.UTILITIES) | {self.original.SELF}
        self.assertEqual(set(prepared), expected_names)
        self.assertNotIn(self.entry.CANDIDATE_ISSUER, prepared)
        self.assertNotIn(self.entry.CANDIDATE_STUDENT, prepared)
        for source, native in self.original.CANDIDATES.items():
            if source != self.entry.CANONICAL_STUDENT:
                self.assertEqual(prepared[native], (HERE / source).read_bytes())
        for name in self.original.UTILITIES:
            self.assertEqual(prepared[name], (HERE / name).read_bytes())
        self.assertEqual(self.entry.BUNDLE, self.bundle)

    def test_all_four_source_pins_match_actual_files(self):
        for name, pin in (
            (self.entry.CANONICAL_ISSUER, self.entry.ORIGINAL_ISSUER_SHA),
            (self.entry.CANONICAL_STUDENT, self.entry.ORIGINAL_STUDENT_SHA),
            (self.entry.CANDIDATE_ISSUER, self.entry.CANDIDATE_ISSUER_SHA),
            (self.entry.CANDIDATE_STUDENT, self.entry.CANDIDATE_STUDENT_SHA),
        ):
            self.assertEqual(sha((HERE / name).read_bytes()), pin, name)

    def test_issuer_inverse_is_exact_and_all_other_ast_nodes_are_unchanged(self):
        original = (HERE / self.entry.CANONICAL_ISSUER).read_bytes()
        candidate = (HERE / self.entry.CANDIDATE_ISSUER).read_bytes()
        before = (repr(self.entry.CANONICAL_STUDENT) + ': ' + repr(self.entry.ORIGINAL_STUDENT_SHA)).encode()
        after = (repr(self.entry.CANONICAL_STUDENT) + ': ' + repr(self.entry.CANDIDATE_STUDENT_SHA)).encode()
        self.assertEqual(candidate.count(after), 1)
        self.assertEqual(candidate.replace(after, before, 1), original)
        before_tree, after_tree = ast.parse(original), ast.parse(candidate)
        before_nodes, after_nodes = [], []
        for tree, target in ((before_tree, before_nodes), (after_tree, after_nodes)):
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PINS' for t in node.targets):
                    continue
                target.append(ast.dump(node, include_attributes=False))
        self.assertEqual(before_nodes, after_nodes)
        issuer = self.entry.bound_installer()
        changed = {k for k in self.original.PINS if self.original.PINS[k] != issuer.PINS[k]}
        self.assertEqual(set(issuer.PINS), set(self.original.PINS))
        self.assertEqual(changed, {self.entry.CANONICAL_STUDENT})

    def test_bad_canonical_or_candidate_bytes_fail_before_exec(self):
        for name in (self.entry.CANONICAL_ISSUER, self.entry.CANONICAL_STUDENT,
                     self.entry.CANDIDATE_ISSUER, self.entry.CANDIDATE_STUDENT):
            with self.subTest(name=name):
                self.entry.BUNDLE = dict(self.bundle)
                self.entry.BUNDLE[name] = b64((HERE / name).read_bytes() + b'\n# foreign\n')
                with mock.patch('builtins.exec', side_effect=AssertionError('unverified execution')):
                    with self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
                        self.entry.bound_installer()

    def test_missing_original_canonical_source_is_not_accepted_as_alias(self):
        self.entry.BUNDLE.pop(self.entry.CANONICAL_STUDENT)
        with self.assertRaisesRegex(RuntimeError, 'BUNDLE_SCOPE'):
            self.entry.bound_installer()

    def test_extra_issuer_change_fails_even_when_its_outer_hash_is_bound(self):
        changed = (HERE / self.entry.CANDIDATE_ISSUER).read_bytes().replace(
            b"DISPATCHER_SERVICE = 'nox-dispatcher-t855u'",
            b"DISPATCHER_SERVICE = 'foreign-service'", 1)
        self.entry.BUNDLE[self.entry.CANDIDATE_ISSUER] = b64(changed)
        with mock.patch.object(self.entry, 'CANDIDATE_ISSUER_SHA', sha(changed)):
            with self.assertRaisesRegex(RuntimeError, 'ISSUER_ONLY_STUDENT_PIN_DELTA'):
                self.entry.bound_installer()

    def test_actual_dependency_pin_still_applies_after_aliasing(self):
        name = self.original.SHARED
        self.entry.BUNDLE[name] = b64((HERE / name).read_bytes() + b'\n# changed shared source\n')
        issuer = self.entry.bound_installer()
        with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            issuer.assets()

    def test_global_operator_placeholder_substitution_preserves_injected_bundle(self):
        raw = (HERE / 'owner_qwen_transport_install_entry.py').read_bytes()
        token = b'__NOX_' + b'BUNDLE_JSON__'
        self.assertEqual(raw.count(token), 1)
        expanded = raw.replace(token, repr(self.bundle).encode())
        entry = load('owner_qwen_transport_install_entry', expanded)
        issuer = entry.bound_installer()
        prepared = issuer.assets()
        self.assertEqual(sha(prepared[entry.CANONICAL_ISSUER]), entry.CANDIDATE_ISSUER_SHA)
        self.assertEqual(sha(prepared[entry.CANONICAL_STUDENT]), entry.CANDIDATE_STUDENT_SHA)
        self.assertEqual(entry.BUNDLE, self.bundle)

    def test_main_calls_only_the_bound_ordinary_installer_once(self):
        actual = types.SimpleNamespace(main=mock.Mock(return_value=2))
        with mock.patch.object(self.entry, 'bound_installer', return_value=actual) as binding:
            self.assertEqual(self.entry.main(), 2)
        binding.assert_called_once_with()
        actual.main.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
