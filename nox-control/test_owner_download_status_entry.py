import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import owner_download_status_entry as entry


class Deployment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'nox'; self.scripts = self.root/'scripts'; self.site = self.root/'site'; self.state = self.root/'state'
        for directory in (self.scripts, self.site, self.state/'media', self.root/'config'):
            directory.mkdir(parents=True, exist_ok=True)
        self.old = {'owner_chat_ui.py': b'BUILD="existing"\n', 'owner-chat-ui.js': b'const previous = true;\n'}
        self.new = {'owner_chat_ui.py': b'BUILD="current"\n', 'owner-chat-ui.js': b'const current = true;\n',
                    'owner_download_status.py': b'DOWNLOAD_SCHEMA="fixture"\n'}
        for name, raw in self.old.items(): self.target(name).write_bytes(raw)
        self.hold = self.state/'TRAIN_HOLD.flag'; self.hold.write_bytes(entry.HOLD_PREFIX)
        self.manifest = self.root/'config/owner_download_manifest.json'; self.manifest.write_bytes(b'{"immutable":true}\n')
        self.accepted = self.state/('owner_chat_upgrade_'+entry.CHAT_REQUEST+'.json')
        self.accepted.write_text(json.dumps({'request': entry.CHAT_REQUEST, 'source_sha': entry.CHAT_SOURCE,
                                           'state': 'LIVE_RESONANCE_REAL_STREAM_S03_HISTORY_ACCEPTED'}))
        values = {'ROOT': self.root, 'SCRIPTS': self.scripts, 'SITE': self.site, 'STATE': self.state,
                  'OLD': {k: entry.digest(v) for k, v in self.old.items()}, 'NEW': {k: entry.digest(v) for k, v in self.new.items()},
                  'BUNDLE': {k: base64.b64encode(v).decode() for k, v in self.new.items()}}
        for name, value in values.items(): self.mock(entry, name, value)
        self.proxy_state = 'RUNNING'; self.operations = []
        def atomic(path, raw):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); path.chmod(0o600)
        self.helper = types.SimpleNamespace(atomic=atomic, service_state=lambda _: {'state': self.proxy_state})
        self.mock(entry, 'helper_module', lambda: self.helper)
        self.mock(entry, 'guards', lambda: {'hold': entry.digest(self.hold.read_bytes()), 'manifest': entry.digest(self.manifest.read_bytes())})
        self.mock(entry, 'model_identity', lambda _: {'pid': 10, 'starttime': '100', 'pgrp': 10})
        self.mock(entry, 'proxy_identity', lambda _: {'pid': 20, 'starttime': '200', 'pgrp': 20})
        self.mock(entry, 'stopped_by_owner', lambda: False)
        self.mock(entry, 'slots_idle', lambda: True)
        self.mock(entry, 'live_probe', lambda: {'nonloopback_peer': True, 'media_verified_files': 4, 'drive_verified_files': 3})
        def stop(*_): self.operations.append('stop_proxy'); self.proxy_state = 'STOPPED'
        def start(*_): self.operations.append('start_proxy'); self.proxy_state = 'RUNNING'
        self.stop = stop; self.start = start
        self.mock(entry, 'stop_proxy', stop); self.mock(entry, 'start_proxy', start)
        env = patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '987654321', 'NOX_OWNER_SOURCE_SHA': 'c'*40})
        env.start(); self.addCleanup(env.stop)

    def mock(self, module, name, value):
        handle = patch.object(module, name, value); handle.start(); self.addCleanup(handle.stop)

    def target(self, name): return (self.site if name.endswith('.js') else self.scripts)/name

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()): return entry.main()

    def receipt(self): return json.loads((self.state/'owner_download_status_987654321.json').read_text())

    def test_exact_install_then_new_request_is_idempotent_without_proxy_restart(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.operations, ['stop_proxy', 'start_proxy'])
        self.assertEqual(self.receipt()['state'], 'LIVE_CURRENT_DOWNLOAD_INVENTORY_VERIFIED')
        for name, raw in self.new.items(): self.assertEqual(self.target(name).read_bytes(), raw)
        self.assertEqual(self.hold.read_bytes(), entry.HOLD_PREFIX)
        self.assertEqual(self.manifest.read_bytes(), b'{"immutable":true}\n')
        self.operations.clear()
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '987654322'}):
            self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.operations, [])
        again = json.loads((self.state/'owner_download_status_987654322.json').read_text())
        self.assertFalse(again['proxy_restarted'])

    def test_unknown_preimage_or_bundle_is_rejected_before_mutation(self):
        self.target('owner_chat_ui.py').write_bytes(b'unknown native edit\n')
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_PREIMAGE'): self.run_main()
        self.assertEqual(self.operations, [])
        self.assertEqual(self.target('owner_chat_ui.py').read_bytes(), b'unknown native edit\n')
        self.target('owner_chat_ui.py').write_bytes(self.old['owner_chat_ui.py'])
        with patch.dict(entry.BUNDLE, {'owner_download_status.py': base64.b64encode(b'changed').decode()}):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE'): self.run_main()
        self.assertEqual(self.operations, [])

    def test_failed_live_acceptance_restores_known_files_and_preserves_model_hold_manifest(self):
        with patch.object(entry, 'live_probe', side_effect=RuntimeError('HOLD_FIXTURE_API')):
            self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.operations, ['stop_proxy', 'start_proxy', 'stop_proxy', 'start_proxy'])
        for name, raw in self.old.items(): self.assertEqual(self.target(name).read_bytes(), raw)
        self.assertTrue(self.receipt()['rollback_verified'])
        self.assertFalse(self.receipt()['model_restarted'])

    def test_restart_health_failure_checks_actual_running_proxy_before_rollback(self):
        count = 0
        def unhealthy(*args):
            nonlocal count
            count += 1; self.start(*args)
            if count == 1: raise RuntimeError('HOLD_FIXTURE_PROXY_HEALTH')
        with patch.object(entry, 'start_proxy', side_effect=unhealthy):
            self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.operations, ['stop_proxy', 'start_proxy', 'stop_proxy', 'start_proxy'])
        self.assertTrue(self.receipt()['rollback_verified'])

    def test_existing_media_controller_lease_defers_before_proxy_or_file_changes(self):
        with entry.lock(self.state/'media/controller.lock'):
            with self.assertRaisesRegex(RuntimeError, 'ACTIVE_OWNER_WORK'): self.run_main()
        self.assertEqual(self.operations, [])
        for name, raw in self.old.items(): self.assertEqual(self.target(name).read_bytes(), raw)

    def test_static_only_update_does_not_restart_proxy(self):
        for name in ('owner_download_status.py', 'owner_chat_ui.py'):
            self.target(name).write_bytes(self.new[name])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.operations, [])
        self.assertFalse(self.receipt()['proxy_restarted'])

    def test_incomplete_or_nonboolean_slot_state_never_allows_proxy_stop(self):
        # setUp replaces the function for other lifecycle tests; execute the
        # real definition in an isolated namespace for this native schema gate.
        import ast
        tree = ast.parse(Path(entry.__file__).read_text())
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == 'slots_idle')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<slot-gate>', 'exec'), namespace)
        for rows, expected in (([{'is_processing': False}]*6, True), ([{'processing': False}]*6, True),
                               ([{}]*6, False), ([{'is_processing': 'false'}]*6, False),
                               ([{'is_processing': False, 'processing': True}]*6, False),
                               ([{'is_processing': False}]*5, False)):
            namespace['local_json'] = lambda *_: rows
            self.assertEqual(namespace['slots_idle'](), expected)

    def test_private_probe_compiles_and_deployment_pins_match_actual_sources(self):
        compile(entry.API_PROBE, '<private-owner-api-probe>', 'exec')
        original = {}
        source = Path(entry.__file__).read_text()
        import ast
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'NEW' for target in node.targets):
                original = ast.literal_eval(node.value)
        for name, sha in original.items():
            self.assertEqual(hashlib.sha256(Path(entry.__file__).with_name(name).read_bytes()).hexdigest(), sha)


if __name__ == '__main__':
    unittest.main()
