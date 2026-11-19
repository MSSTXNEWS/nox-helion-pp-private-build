import ast
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
import textwrap
from unittest import mock


RUNTIME = Path(__file__).parent
NOX_CONTROL = RUNTIME.parents[1]
RELAY = RUNTIME.parent
sys.path[:0] = [str(RUNTIME), str(NOX_CONTROL)]

# The executor package is installed with NOX rather than vendored in this source
# tree. A narrow read-only test double is enough for importing Native.
project_executor = types.ModuleType('owner_project_executor')
project_executor.PROJECT_HANDLER = 'owner_native_project_work'
project_executor.PROJECT_MODE = 'NATIVE_PROJECT_V1'
project_executor.write_atomic = lambda *a, **k: (_ for _ in ()).throw(AssertionError('writer called'))
project_executor.load_plan = lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected plan read'))
project_executor.load_contract_metadata = lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected contract read'))
sys.modules['owner_project_executor'] = project_executor

import owner_systemic_refill as refill
import owner_subagent_dispatcher as dispatcher


RESOURCE = {
    'native_verified': True, 'instance_id': 60509551, 'observed_at': time.time(),
    'stop_active': False, 'source_sha_verified': True, 'owner_scope_verified': True,
    'cgroup_memory_ratio': .1, 'cpu_pressure': 0.0,
}


def load_manifest():
    path = RELAY/'mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json'
    value = json.loads(path.read_bytes())
    value['missions'] = []
    raw = refill.canonical(value)
    refill.validate_manifest(value)
    return value, hashlib.sha256(raw).hexdigest()


class FakeProjects:
    config = {}

    @staticmethod
    def terminal_for_capacity(task):
        return False

    @staticmethod
    def reference(params):
        return {}


class RefillPreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'state/dispatcher').mkdir(parents=True)
        (self.root/'state/owner_maintenance.lock').touch(mode=0o600)
        (self.root/'state/dispatcher/native_subagents.lock').touch(mode=0o600)
        dispatcher.ROOT = self.root
        self.lease_fd = os.open(self.root/'state/dispatcher/native_subagents.lock', os.O_RDWR)
        fcntl.flock(self.lease_fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.manifest, self.manifest_sha = load_manifest()
        self.catalog = {'tasks': []}
        self.config = {
            'schema': dispatcher.SCHEMA, 'policy': {}, 'policy_id': dispatcher.POLICY_ID,
            'owner_request': 'test-request', 'owner_source_sha': 'a'*40,
            'module_pins': {'owner_subagent_dispatcher.py': 'b'*64},
            'instance_id': 60509551, 'owner_authorized': True, 'mode': 'NORMAL',
            'target': 3, 'execution_mode': dispatcher.PROJECT_MODE,
            'leaf_source_pins': {}, 'project_handoff': {},
            'project_executor': {'package_root': str(self.root/'state/dispatcher/package'),
                                 'roots': {}},
            'historical_leaf_source_sha256': [], 'historical_project_source_sha256': [],
            'catalog': self.catalog,
            'catalog_sha256': dispatcher.digest(dispatcher.encoded(self.catalog)),
            'systemic_relay': {'path': str(self.root/'state/dispatcher/package/relay' /
                                          (self.manifest_sha+'.json')),
                               'sha256': self.manifest_sha},
        }
        self.native = dispatcher.Native.__new__(dispatcher.Native)
        self.native.ns = {'_qlock': threading.RLock(), 'save_state': self._unexpected_write}
        self.native.config = copy.deepcopy(self.config)
        self.native.source = 'b'*64
        self.native.projects = FakeProjects()
        self.native.lock = threading.RLock()
        self.native.lease_fd = self.lease_fd
        self.native.state = {'tasks': {}}
        self.native.catalog = self.catalog
        self.native._relay_manifest_cache = {}
        self.native._relay_current_sha256 = None
        self.native.last_resource_admission = {'previous': 'preserve'}
        self.native.owner_allowed = lambda: True
        self.native.stop_active = lambda: False
        self.native._validate_catalog = lambda catalog: True
        self.native._relay_module = lambda: refill
        self.native._relay_manifests = lambda reference, module: {self.manifest_sha: self.manifest}
        self.native._relay_source_pins = lambda module, manifest: {}
        self.native.read_resource_snapshot = lambda leaf_only=None: dict(RESOURCE)
        self.native.allowed_handlers = lambda: {dispatcher.HANDLER, dispatcher.LEAF_HANDLER,
                                                 dispatcher.PROJECT_HANDLER}
        self.native._refill_under_lease = self._unexpected_write
        self.write_calls = []
        self.patch_owner = mock.patch.object(dispatcher, 'owner_config', side_effect=lambda: copy.deepcopy(self.config))
        self.patch_owner.start()

    def tearDown(self):
        self.patch_owner.stop()
        os.close(self.lease_fd)
        self.temp.cleanup()

    def _unexpected_write(self, *args, **kwargs):
        self.write_calls.append((args, kwargs))
        raise AssertionError('write/publish path called')

    def test_refill_required_preview_is_sanitized_and_never_writes(self):
        state_before = copy.deepcopy(self.native.state)
        for name in ('atomic', 'write_json_atomic', 'write_package', 'publish'):
            setattr(project_executor, name, self._unexpected_write)
        with mock.patch.object(project_executor, 'write_atomic', side_effect=self._unexpected_write):
            result = self.native.preview_refill_request()
        self.assertEqual(result['state'], 'REFILL_REQUIRED')
        self.assertEqual(result['refill_request']['schema'], 'NOX_SYSTEMIC_REFILL_REQUEST_V1')
        self.assertEqual(result['refill_request']['request_id'], result['fingerprint'])
        self.assertFalse(result['refill_request']['original_task_accepted'])
        self.assertNotIn('research_topics', result['refill_request'])
        self.assertNotIn('required_next_step', result['refill_request'])
        self.assertEqual(self.native.last_resource_admission, {'previous': 'preserve'})
        self.assertEqual(self.native._relay_manifest_cache, {})
        self.assertEqual(self.native.state, state_before)
        self.assertEqual(self.write_calls, [])

    def test_missing_lease_holds_before_resource_or_selector(self):
        self.native.lease_fd = None
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_STOP_OR_WRITER_LEASE'):
            self.native.preview_refill_request()
        self.assertEqual(self.write_calls, [])

    def test_replaced_lease_inode_holds(self):
        path = self.root/'state/dispatcher/native_subagents.lock'
        replaced = path.with_suffix('.old')
        path.rename(replaced)
        path.touch(mode=0o600)
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_STOP_OR_WRITER_LEASE'):
            self.native.preview_refill_request()
        self.assertEqual(self.write_calls, [])

    def test_stop_holds_before_resource_or_selector(self):
        self.native.stop_active = lambda: True
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_STOP_OR_WRITER_LEASE'):
            self.native.preview_refill_request()
        self.assertEqual(self.write_calls, [])

    def test_callback_sha_mismatch_holds(self):
        self.config['module_pins']['owner_subagent_dispatcher.py'] = 'c'*64
        self.native.config = copy.deepcopy(self.config)
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_CALLBACK_OR_CATALOG'):
            self.native.preview_refill_request()
        self.assertEqual(self.write_calls, [])

    def test_stale_resource_observation_holds(self):
        self.native.read_resource_snapshot = lambda leaf_only=None: {**RESOURCE,
            'observed_at': time.time()-6}
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_RESOURCE_STALE'):
            self.native.preview_refill_request()

    def test_resource_pressure_holds(self):
        self.native.read_resource_snapshot = lambda leaf_only=None: {**RESOURCE,
            'cgroup_memory_ratio': .99}
        with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_RESOURCE_GATE'):
            self.native.preview_refill_request()

    def test_capacity_wait_does_not_emit_refill_request(self):
        manifest_path = RELAY/'mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json'
        manifest = json.loads(manifest_path.read_bytes())
        mission = manifest['missions'][0]
        self.manifest = manifest
        self.manifest_sha = refill.digest(manifest)
        self.config['systemic_relay'] = {'path': str(self.root/'state/dispatcher/package/relay' /
            (self.manifest_sha+'.json')), 'sha256': self.manifest_sha}
        self.native.config = copy.deepcopy(self.config)
        self.native._relay_manifests = lambda reference, module: {self.manifest_sha: self.manifest}
        self.native._relay_source_pins = lambda module, value: {
            mission['root_id']: {row['path']: row['sha256'] for row in mission['context']}}
        self.native.state = {'tasks': {f'busy-{i}': {
            'handler': dispatcher.HANDLER, 'status': 'running'} for i in range(3)}}
        result = self.native.preview_refill_request()
        self.assertEqual(result['state'], 'WAIT_EXISTING_WORK')
        self.assertIsNone(result['refill_request'])
        self.assertEqual(result['slots_available'], 0)

    def test_active_source_reservation_blocks_refill_request(self):
        manifest_path = RELAY/'mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json'
        manifest = json.loads(manifest_path.read_bytes())
        mission = manifest['missions'][0]
        self.manifest = manifest
        self.manifest_sha = refill.digest(manifest)
        self.config['systemic_relay'] = {'path': str(self.root/'state/dispatcher/package/relay' /
            (self.manifest_sha+'.json')), 'sha256': self.manifest_sha}
        self.native.config = copy.deepcopy(self.config)
        self.native._relay_manifests = lambda reference, module: {self.manifest_sha: self.manifest}
        self.native._relay_source_pins = lambda module, value: {
            mission['root_id']: {row['path']: row['sha256'] for row in mission['context']}}
        reserved = mission['editable_paths'][0]
        self.native.state = {'tasks': {'active-project': {
            'handler': dispatcher.PROJECT_HANDLER, 'status': 'running', 'params': {}}}}
        with mock.patch.object(project_executor, 'load_contract_metadata', return_value={
                'root_id':mission['root_id'],'editable_paths':[reserved]}):
            result = self.native.preview_refill_request()
        self.assertEqual(result['state'], 'WAIT_EXISTING_WORK')
        self.assertIsNone(result['refill_request'])
        self.assertEqual(result['reserved_source_count'], 1)

    def test_state_change_during_selector_holds(self):
        original = refill.select_next

        def mutate_then_select(*args, **kwargs):
            self.native.state['tasks']['changed'] = {'handler':dispatcher.HANDLER,'status':'done'}
            return original(*args, **kwargs)

        with mock.patch.object(refill, 'select_next', side_effect=mutate_then_select):
            with self.assertRaisesRegex(dispatcher.GateError, 'HOLD_REFILL_PREVIEW_FINAL_STATE_CHANGED'):
                self.native.preview_refill_request()
        self.assertEqual(self.write_calls, [])

    def test_call_graph_has_no_durable_writer_or_publisher_edges(self):
        names = ('preview_refill_request', '_preview_writer_lease_current',
                 '_preview_maintenance_lease', '_preview_current_state',
                 '_sanitize_refill_preview', '_relay_module', '_relay_manifests',
                 '_relay_source_pins', 'read_resource_snapshot', '_leaf_only_work',
                 '_validate_catalog')
        forbidden = {'write_atomic', 'atomic', 'save_state', 'publish',
                     'publisher_entry', 'write_package', '_refill_under_lease'}
        for name in names:
            method = getattr(dispatcher.Native, name)
            tree = ast.parse(textwrap.dedent(__import__('inspect').getsource(method)))
            calls = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                target = node.func
                calls.add(target.attr if isinstance(target, ast.Attribute)
                          else target.id if isinstance(target, ast.Name) else '')
            self.assertFalse(forbidden & calls, f'{name}: {forbidden & calls}')
            source = __import__('inspect').getsource(method)
            self.assertNotRegex(source, r'os\.(?:O_CREAT|O_WRONLY|O_RDWR)')
        for name in ('select_next','validate_manifest','_outcomes','_binding','_input','_contract'):
            tree = ast.parse(textwrap.dedent(__import__('inspect').getsource(getattr(refill,name))))
            calls = set()
            for node in ast.walk(tree):
                if isinstance(node,ast.Call):
                    target=node.func
                    calls.add(target.attr if isinstance(target,ast.Attribute)
                              else target.id if isinstance(target,ast.Name) else '')
            self.assertFalse(forbidden & calls, f'refill.{name}: {forbidden & calls}')


if __name__ == '__main__':
    unittest.main()
