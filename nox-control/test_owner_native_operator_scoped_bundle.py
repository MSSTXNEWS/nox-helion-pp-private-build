"""Check source-only payload selection; no provider, SSH or native calls."""
import ast
import base64
import hashlib
import os
from pathlib import Path
import types
import unittest
from unittest import mock


HERE = Path(__file__).parent
ROOT = HERE.parent
RAW = (HERE / 'owner_native_operator_scoped_bundle.py').read_bytes()
BASE_SHA = '0aa8df81e9cfdeac71ceabd77f4e1a6b5287ececb8f650cc51f7195b34d1210e'


def load(path, raw=None):
    module = types.ModuleType('_scoped_test_' + path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes() if raw is None else raw, str(path), 'exec'), module.__dict__)
    return module


def original_bytes():
    start, end = RAW.index(b'SCOPED_REPAIR_BUNDLES='), RAW.index(b'def authorize_event(')
    restored = RAW[:start] + RAW[end:]
    before = b"for path in repair_bundle_paths(action,FILES[action],('nox-control/nox_cold_drive.py'"
    after = b"for path in ('nox-control/nox_cold_drive.py'"
    assert restored.count(before) == 1
    restored = restored.replace(before, after, 1)
    before = b"'coordination/NOX_STORAGE_STREAMING_20261115/download_manifest.json')):"
    after = b"'coordination/NOX_STORAGE_STREAMING_20261115/download_manifest.json'):"
    assert restored.count(before) == 1
    return restored.replace(before, after, 1)


M = load(HERE / 'owner_native_operator_scoped_bundle.py')
BASE = original_bytes()
TREE = ast.parse(BASE)
LOOP = max((node for node in ast.walk(TREE) if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name) and node.target.id == 'path'
            and isinstance(node.iter, ast.Tuple)), key=lambda node: len(node.iter.elts))
PATHS = ast.literal_eval(LOOP.iter)
HELD = 'nox-control/owner_qwen_held_media_smoke_entry.py'
TRANSPORT = 'nox-control/owner_qwen_transport_install_entry.py'


class ScopeTests(unittest.TestCase):
    def setUp(self):
        previous = Path.cwd(); os.chdir(ROOT)
        self.addCleanup(os.chdir, previous)

    def test_exact_remote_original_is_restored_by_only_bundle_inverse(self):
        self.assertEqual(hashlib.sha256(BASE).hexdigest(), BASE_SHA)
        self.assertEqual(len(PATHS), 150)
        self.assertEqual(len({Path(p).name for p in PATHS}), 150)
        tree = ast.parse(RAW)
        class Inverse(ast.NodeTransformer):
            def visit_Assign(self, node):
                return None if any(isinstance(t, ast.Name) and t.id in {'SCOPED_REPAIR_BUNDLES', 'SCOPED_REPAIR_EXTRA_PATHS'} for t in node.targets) else node
            def visit_FunctionDef(self, node):
                return None if node.name == 'repair_bundle_paths' else self.generic_visit(node)
            def visit_For(self, node):
                self.generic_visit(node)
                if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'repair_bundle_paths':
                    self.assert_call(node.iter)
                    node.iter = node.iter.args[2]
                return node
            @staticmethod
            def assert_call(call):
                assert len(call.args) == 3 and not call.keywords
                assert ast.dump(call.args[0]) == ast.dump(ast.Name(id='action', ctx=ast.Load()))
                assert ast.dump(call.args[1]) == ast.dump(ast.parse('FILES[action]', mode='eval').body)
        self.assertEqual(ast.dump(Inverse().visit(tree), include_attributes=False),
                         ast.dump(TREE, include_attributes=False))

    def test_held_selected_set_is_exactly_core_and_its_actual_four_pins(self):
        core = load(HERE / 'owner_qwen_held_media_smoke.py')
        selected = M.repair_bundle_paths('repair', HELD, PATHS)
        expected = {'owner_qwen_held_media_smoke.py'} | set(core.PINS)
        self.assertEqual({Path(p).name for p in selected}, expected)
        self.assertEqual(len(selected), 5)
        for path in selected:
            pin = core.PINS.get(Path(path).name, '51b42fef5455fd041a2cadb19c8ca86b3e35e7ad45b2315cdbe4ae5b82d24200')
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), pin)

    def test_transport_set_derives_from_actual_assets_and_keeps_original_alias_checks(self):
        original = load(HERE / 'owner_qwen_revision_install.py')
        wrapper = load(HERE / 'owner_qwen_transport_install_entry.py')
        selected = M.repair_bundle_paths('repair', TRANSPORT, PATHS)
        expected = set(original.CANDIDATES) | set(original.UTILITIES) | {
            original.SELF, wrapper.CANDIDATE_ISSUER, wrapper.CANDIDATE_STUDENT}
        self.assertEqual({Path(p).name for p in selected}, expected)
        self.assertEqual(len(selected), 14)
        wrapper.BUNDLE = {Path(p).name: base64.b64encode(Path(p).read_bytes()).decode('ascii') for p in selected}
        assets = wrapper.bound_installer().assets()
        self.assertEqual(hashlib.sha256(assets[wrapper.CANONICAL_ISSUER]).hexdigest(), wrapper.CANDIDATE_ISSUER_SHA)
        self.assertEqual(hashlib.sha256(assets[wrapper.CANONICAL_STUDENT]).hexdigest(), wrapper.CANDIDATE_STUDENT_SHA)
        self.assertEqual(set(assets), set(original.CANDIDATES.values()) | set(original.UTILITIES) | {original.SELF})

    def test_missing_inventory_member_fails_instead_of_partial_bundle(self):
        missing = tuple(p for p in PATHS if Path(p).name != 'owner_native_repair.py')
        with self.assertRaisesRegex(RuntimeError, 'MISSING_SOURCE'):
            M.repair_bundle_paths('repair', HELD, missing)

    def test_duplicate_selected_basename_fails_even_if_one_path_would_be_missing(self):
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_SOURCE'):
            M.repair_bundle_paths('repair', HELD, PATHS + ('elsewhere/owner_native_repair.py',))

    def test_duplicate_allowlist_fails(self):
        with mock.patch.dict(M.SCOPED_REPAIR_BUNDLES, {HELD: M.SCOPED_REPAIR_BUNDLES[HELD] * 2}):
            with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_ALLOWLIST'):
                M.repair_bundle_paths('repair', HELD, PATHS)

    def test_missing_disk_file_is_not_silently_skipped(self):
        is_file = Path.is_file
        def checked(path):
            return False if path.name == 'owner_qwen_transport_revision_install.py' else is_file(path)
        with mock.patch.object(Path, 'is_file', checked):
            with self.assertRaisesRegex(RuntimeError, 'MISSING_FILE'):
                M.repair_bundle_paths('repair', TRANSPORT, PATHS)

    def test_unmapped_entrypoints_and_all_other_actions_preserve_original_inventory(self):
        with mock.patch.object(Path, 'is_file', side_effect=AssertionError('unmapped must not add validation')):
            for action, entry in (('stage', TRANSPORT), ('inspect', HELD), ('audit', HELD),
                                  ('lifeline', TRANSPORT), ('repair', 'nox-control/owner_native_repair.py')):
                self.assertIs(M.repair_bundle_paths(action, entry, PATHS), PATHS)
        self.assertNotIn('nox-control/owner_qwen_transport_revision_install.py', PATHS)


if __name__ == '__main__':
    unittest.main()
