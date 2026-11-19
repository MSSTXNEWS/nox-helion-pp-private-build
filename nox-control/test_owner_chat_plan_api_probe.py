"""Static-source privacy, no-execution and stable descriptor regression checks."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).with_name('owner_chat_plan_api_probe.py')
SPEC = importlib.util.spec_from_file_location('static_plan_probe', PATH)
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)


class ProjectionTests(unittest.TestCase):
    def test_tools_export_only_schema_shapes_and_admin_protocol_identifiers(self):
        tools = [
            {'type': 'function', 'function': {'name': 'run_admin', 'description': 'PRIVATE_DESCRIPTION_ABC',
                'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['action'],
                    'properties': {'action': {'type': 'string', 'enum': ['status', 'queue_add', 'private_key_xyz',
                        'https://private.invalid/credential']}, 'token': {'type': 'string', 'default': 'SECRET_DEFAULT'}}}}},
            {'type': 'function', 'function': {'name': 'read_file', 'parameters': {'type': 'object',
                'properties': {'file_id': {'type': 'string', 'enum': ['PRIVATE_FILE_ID']}}}}},
        ]
        raw = ('TOOLS = ' + repr(tools) + '\n').encode()
        result = P.projection(raw); output = json.dumps(result)
        self.assertEqual(result['tool_registry']['tools'][0]['action_enum']['values'], ['queue_add', 'status'])
        self.assertEqual(result['tool_registry']['tools'][0]['action_enum']['omitted_values'], 2)
        self.assertEqual(result['tool_registry']['tools'][1]['parameter_types'], {'file_id': 'string'})
        for hidden in ('PRIVATE_DESCRIPTION_ABC', 'SECRET_DEFAULT', 'PRIVATE_FILE_ID', 'private.invalid', 'private_key_xyz'):
            self.assertNotIn(hidden, output)

    def test_source_is_parsed_not_imported_or_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            forbidden = Path(temp) / 'must-not-exist'
            raw = ("open(" + repr(str(forbidden)) + ", 'w').write('SECRET')\n"
                   "def enqueue_task(task, owner):\n"
                   "    verify_owner(owner)\n"
                   "    with queue_lock():\n"
                   "        return write_task(task)\n").encode()
            result = P.projection(raw)
            self.assertFalse(forbidden.exists())
            row = result['selected_functions'][0]
            self.assertEqual(row['name'], 'enqueue_task')
            self.assertEqual(row['parameters'], ['task', 'owner'])
            self.assertEqual(row['calls'], ['queue_lock', 'verify_owner', 'write_task'])
            self.assertFalse(result['code_executed']); self.assertFalse(result['enqueue_safety_or_authorization_verified'])
            self.assertNotIn('SECRET', json.dumps(result)); self.assertNotIn(str(forbidden), json.dumps(result))

    def test_confirmation_and_action_branches_are_projected_without_arguments(self):
        raw = b'''ACTIONS = {'status': lambda: None, 'queue_add': lambda: None}
def run_action(action, args, confirmed=False):
    if action in ('status', 'queue_add'):
        return enqueue(args, 'PRIVATE_TOKEN_IN_CALL')
def dispatch(name, arguments):
    if name == 'run_admin':
        return run_action('status', arguments, confirmed=False)
'''
        result = P.projection(raw)
        self.assertEqual(result['literal_action_tables']['ACTIONS']['values'], ['queue_add', 'status'])
        rows = {r['name']: r for r in result['selected_functions']}
        self.assertEqual(rows['run_action']['action_or_tool_branches']['values'], ['queue_add', 'status'])
        self.assertEqual(rows['dispatch']['run_action_confirmed_arguments'], [False])
        self.assertNotIn('PRIVATE_TOKEN_IN_CALL', json.dumps(result))

    def test_dynamic_tool_registry_is_unknown_and_not_evaluated(self):
        raw = b"TOOLS = dangerous_registry_call()\ndef submit_task(task):\n    return unknown(task)\n"
        result = P.projection(raw)
        self.assertEqual(result['tool_registry'], {'state': 'DYNAMIC_UNRESOLVED', 'tools': []})
        self.assertEqual(result['selected_functions'][0]['name'], 'submit_task')

    def test_only_api_route_shapes_and_no_private_route_values(self):
        raw = b'''@app.post('/api/nox/tasks/submit')
async def submit_task(payload):
    return await checked_enqueue(payload)
@app.get('/private/SECRET_PATH')
def private_file():
    return 'PRIVATE_CONTENT'
'''
        result = P.projection(raw)
        self.assertEqual(result['literal_routes'], [{'method': 'POST', 'path': '/api/nox/tasks/submit', 'function': 'submit_task'}])
        self.assertNotIn('SECRET_PATH', json.dumps(result)); self.assertNotIn('PRIVATE_CONTENT', json.dumps(result))


class DescriptorTests(unittest.TestCase):
    def test_read_only_source_hash_and_historical_drift_are_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'nox_tools.py'; raw = b'TOOLS = []\n'; path.write_bytes(raw); path.chmod(0o664)
            before = path.stat()
            with mock.patch.object(P, 'TARGETS', (('TOOLS', path, 'a' * 64),)):
                result = P.observe('TOOLS', path, 'a' * 64)
            self.assertEqual(result['state'], 'STATIC_API_STRUCTURE_OBSERVED')
            self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertFalse(result['historical_source_matches'])
            self.assertEqual(result['mode_octal'], '0664')
            self.assertEqual(P.identity(before), P.identity(path.stat()))

    def test_symlink_and_oversize_are_not_followed_or_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'nox_tools.py'; private = root / 'private'
            private.write_bytes(b'SECRET'); path.symlink_to(private)
            with mock.patch.object(P, 'TARGETS', (('TOOLS', path, None),)):
                observed = P.observe('TOOLS', path, None)
                self.assertEqual(observed['state'], 'STRUCTURE_UNAVAILABLE')
                self.assertNotIn('SECRET', json.dumps(observed))
                path.unlink(); path.write_bytes(b'x' * 10)
                with mock.patch.object(P, 'MAX_FILE', 9), mock.patch.object(P.os, 'read', side_effect=AssertionError('oversize read')):
                    observed = P.observe('TOOLS', path, None)
                self.assertEqual(observed['reason'], 'HOLD_CHAT_PLAN_API_SOURCE_SCOPE')

    def test_named_replacement_during_read_never_becomes_stable_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'nox_tools.py'; path.write_bytes(b'TOOLS = []\n')
            other = root / 'foreign'; other.write_bytes(path.read_bytes())
            original = os.read; replaced = False
            def race(fd, size):
                nonlocal replaced
                value = original(fd, size)
                if value and not replaced:
                    replaced = True; os.replace(other, path)
                return value
            with mock.patch.object(P, 'TARGETS', (('TOOLS', path, None),)), mock.patch.object(P.os, 'read', side_effect=race):
                result = P.observe('TOOLS', path, None)
            self.assertEqual(result['reason'], 'HOLD_CHAT_PLAN_API_SOURCE_CHANGED')

    def test_all_missing_sources_remain_partial_without_trace_or_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing.py'; output = io.StringIO()
            with mock.patch.object(P, 'TARGETS', (('TOOLS', path, None),)), \
                 mock.patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123456', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
                 contextlib.redirect_stdout(output):
                result = P.main()
            self.assertEqual(result, 2); self.assertEqual(list(Path(temp).iterdir()), [])
            lines = output.getvalue().splitlines()
            payload = json.loads(lines[0].split('=', 1)[1])['data']
            self.assertFalse(payload['observation_complete']); self.assertFalse(payload['task_enqueued'])
            self.assertEqual(payload['files_written'], 0)
            self.assertEqual(lines[-1], 'NOX_MAINT_REPAIR_COMPLETE=false')
            self.assertNotIn(str(path), output.getvalue())


if __name__ == '__main__':
    unittest.main()
