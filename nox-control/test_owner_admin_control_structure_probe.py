"""Delegated binding, static-only privacy and bounded descriptor regressions."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name('owner_admin_control_structure_probe.py')
SPEC = importlib.util.spec_from_file_location('admin_structure_probe', PATH)
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)
ADMIN = b'''try:
    from nox_control_t878u import handle as _ctl_handle_t878u
except ImportError:
    _ctl_handle_t878u = None
def run_action(action, args, confirmed=False):
    if _ctl_handle_t878u:
        result = _ctl_handle_t878u(action, args)
        if result.get('handled'): return result
    return {'ok': False, 'text': 'PRIVATE_FALLBACK_BODY'}
'''


class StructureTests(unittest.TestCase):
    def test_one_import_with_none_fallback_does_not_claim_runtime_binding(self):
        binding = P.resolve_handler(ast.parse(ADMIN))
        self.assertEqual(binding['state'], 'ONE_LOCAL_STATIC_IMPORT')
        self.assertEqual((binding['module'], binding['handler']), ('nox_control_t878u', 'handle'))
        self.assertEqual(binding['null_import_fallback_count'], 1)
        self.assertFalse(binding['runtime_binding_verified'])

    def test_dynamic_nonlocal_and_multiple_bindings_never_choose_a_file(self):
        cases = [
            b"from package.control import handle as _ctl_handle_t878u\n",
            b"from .control import handle as _ctl_handle_t878u\n",
            ADMIN + b"_ctl_handle_t878u = dynamic_lookup()\n",
            ADMIN + b"from other import handle as _ctl_handle_t878u\n",
            b"_ctl_handle_t878u = __import__('private').handle\n",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                result = P.resolve_handler(ast.parse(raw))
                self.assertNotEqual(result['state'], 'ONE_LOCAL_STATIC_IMPORT')
                self.assertNotIn('module', result)

    def test_return_shapes_calls_and_aliases_omit_body_commands_and_credentials(self):
        raw = b'''ALIASES = {'queue_status': 'status', 'private_key_value': 'SECRET_ALIAS'}
def handle(action, args):
    aliases = {'audit': 'queue_audit'}
    if action.startswith('queue_'):
        return {'handled': True, 'ok': True, 'text': 'PRIVATE_TEXT', 'token': 'SECRET_TOKEN'}
    if action == 'status':
        run('PRIVATE_COMMAND_WITH_KEY')
        return {'state': 'OBSERVED', 'result': secret_value}
    return None
'''
        result = P.project(raw, 'handle'); text = json.dumps(result)
        self.assertTrue(result['handler_declared_at_module_scope'])
        handler = next(x for x in result['selected_functions'] if x['name'] == 'handle')
        self.assertEqual(handler['parameters'], ['action', 'args'])
        self.assertEqual(handler['action_branches'], ['status'])
        self.assertEqual(handler['action_prefixes'], ['queue_'])
        self.assertIn('run', handler['calls'])
        self.assertEqual(handler['return_shapes'][-1], {'kind': 'NONE'})
        for private in ('PRIVATE_TEXT', 'SECRET_TOKEN', 'SECRET_ALIAS', 'PRIVATE_COMMAND_WITH_KEY', 'private_key_value'):
            self.assertNotIn(private, text)

    def test_static_observation_never_executes_helper_module_or_handler(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sentinel = root / 'forbidden'
            helper = ("open(" + repr(str(sentinel)) + ", 'w').write('PRIVATE')\n"
                      "def handle(action,args):\n    return write_queue(args)\n").encode()
            (root / 'nox_admin.py').write_bytes(ADMIN)
            (root / 'nox_control_t878u.py').write_bytes(helper)
            with patch.object(P, 'ROOT', root), patch.object(P, 'ADMIN_SHA', hashlib.sha256(ADMIN).hexdigest()):
                result = P.observe()
            self.assertFalse(sentinel.exists())
            self.assertTrue(result['helper_observed'])
            self.assertEqual(result['helper']['sha256'], hashlib.sha256(helper).hexdigest())
            self.assertEqual(set(x.name for x in root.iterdir()), {'nox_admin.py', 'nox_control_t878u.py'})
            self.assertNotIn(str(sentinel), json.dumps(result))

    def test_admin_preimage_mismatch_stops_before_helper_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'nox_admin.py').write_bytes(ADMIN)
            original = P.read_source; names = []
            def reading(name, allowed):
                names.append(name); return original(name, allowed)
            with patch.object(P, 'ROOT', root), patch.object(P, 'read_source', side_effect=reading):
                with self.assertRaisesRegex(P.Hold, 'ADMIN_PIN'): P.observe()
            self.assertEqual(names, ['nox_admin.py'])

    def test_missing_helper_preserves_resolved_binding_and_admin_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'nox_admin.py').write_bytes(ADMIN)
            with patch.object(P, 'ROOT', root), patch.object(P, 'ADMIN_SHA', hashlib.sha256(ADMIN).hexdigest()):
                result = P.observe()
            self.assertEqual(result['state'], 'DELEGATED_CONTROL_SOURCE_UNAVAILABLE')
            self.assertEqual(result['reason'], 'ENOENT')
            self.assertEqual(result['binding']['module'], 'nox_control_t878u')
            self.assertFalse(result['observation_complete'])

    def test_symlink_and_oversize_cannot_expand_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); target = root / 'private.py'; target.write_bytes(b'PRIVATE')
            link = root / 'nox_control_t878u.py'; link.symlink_to(target)
            with patch.object(P, 'ROOT', root):
                with self.assertRaises(OSError): P.read_source(link.name, {link.name})
                with self.assertRaisesRegex(P.Hold, 'FIXED_SOURCE'): P.read_source('../private.py', {'../private.py'})
                link.unlink(); link.write_bytes(b'x' * 10)
                with patch.object(P, 'MAX_FILE', 9), patch.object(P.os, 'read', side_effect=AssertionError('oversize read')):
                    with self.assertRaisesRegex(P.Hold, 'SOURCE_METADATA'): P.read_source(link.name, {link.name})

    def test_atomic_foreign_same_bytes_replacement_is_not_stable_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'nox_admin.py'; path.write_bytes(ADMIN)
            other = root / 'foreign.py'; other.write_bytes(ADMIN)
            original = os.read; changed = False
            def raced(fd, size):
                nonlocal changed
                value = original(fd, size)
                if value and not changed:
                    changed = True; os.replace(other, path)
                return value
            with patch.object(P, 'ROOT', root), patch.object(P.os, 'read', side_effect=raced):
                with self.assertRaisesRegex(P.Hold, 'SOURCE_CHANGED'): P.read_source(path.name, {path.name})


if __name__ == '__main__':
    unittest.main()
