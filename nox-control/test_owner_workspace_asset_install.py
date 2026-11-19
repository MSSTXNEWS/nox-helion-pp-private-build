"""Local filesystem fixtures only: no native endpoints or service actions."""
import ast
import base64
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_workspace_asset_install as w

HERE = Path(__file__).resolve().parent
JS = HERE.parent / 'coordination/onepass' / w.CANDIDATE
BUNDLE = {name: base64.b64encode((JS if name == w.CANDIDATE else HERE / name).read_bytes()).decode()
          for name in w.DEPENDENCIES}
OLD = b'original-workspace-fixture'
NEW = JS.read_bytes()


class WorkspaceInstallerTests(unittest.TestCase):
    def library(self):
        with patch.object(w, 'BUNDLE', BUNDLE):
            return w.prepared_library()[0]

    def run_fixture(self, fail=None):
        b = self.library(); output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary); state = root / 'state'; state.mkdir(mode=0o700)
            site_root = root / 'site'; site_root.mkdir(mode=0o755)
            site = site_root / 'pc'; site.mkdir(mode=0o755)
            target = site / 'workspace.js'; target.write_bytes(OLD); target.chmod(0o644)
            original_inode = target.stat().st_ino
            (state / 'owner_maintenance.lock').touch(mode=0o600)
            for name, value in {'ROOT': root, 'STATE': state, 'SITE': site,
                'AREA': state / 'owner_workspace_asset_installs', 'OLD_SHA': b.digest(OLD), 'OLD_BYTES': len(OLD)}.items():
                stack.enter_context(patch.object(b, name, value))
            stack.enter_context(patch.object(w, 'OLD_SHA', b.digest(OLD)))
            stack.enter_context(patch.object(w, 'OLD_BYTES', len(OLD)))
            old_require = w.require
            stack.enter_context(patch.object(w, 'require', side_effect=lambda ok, code:
                old_require(True if code == 'ROOT_REQUIRED' else ok, code)))
            stack.enter_context(patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}))
            auth_calls = []; snapshots = []
            client = types.SimpleNamespace(cookie='never-export-private-cookie', close=lambda: None)
            def authenticate():
                auth_calls.append(True); return client
            auth = types.SimpleNamespace(OwnerClient=types.SimpleNamespace(authenticate=authenticate))
            stack.enter_context(patch.object(w, 'prepared_library', return_value=(b, NEW, auth, object())))
            before = {'boot_id': 'fixture', 'model': {'pid': 7637}, 'proxy': {'pid': 101},
                      'trainer': {'state': 'FATAL', 'pid': None}}
            stack.enter_context(patch.object(b, 'identities', return_value=before))
            stack.enter_context(patch.object(b, 'source_guards', return_value={'protected': 'hash'}))
            stack.enter_context(patch.object(b, 'health', return_value={'8080': 200, '8081': 200, '8082': 200}))
            stack.enter_context(patch.object(b, 'local_address', return_value='192.0.2.1'))
            for name in ('main', 'protect_directory', 'permission_intent', 'rollback_transaction'):
                stack.enter_context(patch.object(b, name, side_effect=AssertionError('old workflow must not run')))
            def training(*_):
                snapshots.append(True)
                return {'state': 'FATAL', 'pid': None, 'flag': 'changed' if fail == 'training' and len(snapshots) == 3 else 'same'}
            stack.enter_context(patch.object(w, 'training_snapshot', side_effect=training))
            def http(host, path, cookie=None, maximum=262144):
                self.assertEqual(host, '192.0.2.1')
                if path == b.PAGE:
                    return 200, b'<script defer src="./workspace.js"></script>'
                self.assertEqual(path, '/nox-web-v29/pc/workspace.js')
                if cookie is None:
                    return 401, b''
                self.assertEqual(cookie, client.cookie)
                current = target.read_bytes()
                if current == NEW and fail == 'http':
                    return 200, b'incorrect bytes'
                if current == NEW and fail == 'foreign':
                    other = site / 'other.js'; other.write_bytes(NEW); other.chmod(0o644)
                    os.replace(other, target)
                return 200, current
            stack.enter_context(patch.object(b, 'http_get', side_effect=http))
            if fail == 'preimage':
                target.write_bytes(b'foreign preimage')
            if fail == 'receipt':
                original_json = b.private_json
                def bad_receipt(parent, name, value):
                    result = original_json(parent, name, value)
                    if name == 'receipt.json':
                        raise RuntimeError('HOLD_FIXTURE_LATE_RECEIPT')
                    return result
                stack.enter_context(patch.object(b, 'private_json', side_effect=bad_receipt))
            if fail == 'after_kernel':
                real_exchange = b.exchange; calls = []
                def kernel_edge(*args):
                    real_exchange(*args); calls.append(True)
                    if len(calls) == 1:
                        raise RuntimeError('HOLD_FIXTURE_AFTER_KERNEL')
                stack.enter_context(patch.object(b, 'exchange', side_effect=kernel_edge))
            with redirect_stdout(output):
                rc = w.main()
            rows = [json.loads(line.split('=', 1)[1]) for line in output.getvalue().splitlines()
                    if line.startswith('NOX_MAINT_REPAIR=')]
            result = rows[0]['data']; final = target.read_bytes(); final_inode = target.stat().st_ino
            journal = b.AREA / '123'
            backup = (journal / 'original.js').read_bytes() if journal.exists() else None
            self.assertNotIn(client.cookie, output.getvalue())
            self.assertEqual(site.stat().st_mode & 0o777, 0o755)
            self.assertEqual(site_root.stat().st_mode & 0o777, 0o755)
            return rc, result, final, original_inode, final_inode, backup, auth_calls, rows

    def test_actual_bundle_pins_paths_and_reused_rollback_functions(self):
        b = self.library()
        self.assertEqual(str(b.SITE), '/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc')
        self.assertEqual(b.ASSET, 'workspace.js')
        self.assertEqual(len(NEW), 7278)
        self.assertEqual(b.digest(NEW), w.NEW_SHA)
        self.assertEqual(b.digest((HERE / w.BASE_NAME).read_bytes()), w.BASE_SHA)
        self.assertEqual(b.PROTECTED[b.SITE.parent / 'nox-v135-resonance-owner-bridge.js'], w.COALESCED_SHA)
        tree = ast.parse(Path(w.__file__).read_text())
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertFalse(calls & {'b.main', 'b.protect_directory', 'b.permission_intent', 'os.chmod', 'os.fchmod',
                                  'helper.command', 'helper.run', 'subprocess.run', 'subprocess.Popen'})

    def test_missing_or_changed_bundle_fails_before_native_action(self):
        for bundle in ({}, {**BUNDLE, w.BASE_NAME: base64.b64encode(b'foreign').decode()}):
            with patch.object(w, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_'):
                w.prepared_library()

    def test_success_is_http_proof_not_browser_behavior(self):
        rc, row, final, _, _, backup, _, rows = self.run_fixture()
        self.assertEqual(rc, 0); self.assertTrue(row['success']); self.assertEqual(final, NEW)
        self.assertEqual(backup, OLD); self.assertFalse(row['browser_acceptance_verified'])
        self.assertFalse(row['directory_permissions_modified']); self.assertFalse(row['proxy_restarted'])
        self.assertTrue(row['training_sources_flags_and_observed_processes_preserved'])
        self.assertEqual(rows[1]['kind'], 'workspace_asset_context')

    def test_wrong_preimage_stops_before_auth_and_journal(self):
        rc, row, final, _, _, backup, auth, _ = self.run_fixture('preimage')
        self.assertEqual(rc, 2); self.assertFalse(row['success']); self.assertEqual(final, b'foreign preimage')
        self.assertEqual(auth, []); self.assertIsNone(backup)

    def test_http_failure_restores_original_inode(self):
        rc, row, final, inode, final_inode, backup, _, _ = self.run_fixture('http')
        self.assertEqual(rc, 2); self.assertTrue(row['rollback_verified'])
        self.assertEqual((final, final_inode, backup), (OLD, inode, OLD))

    def test_foreign_same_bytes_inode_is_preserved(self):
        rc, row, final, old_inode, final_inode, backup, _, _ = self.run_fixture('foreign')
        self.assertEqual(rc, 2); self.assertFalse(row['rollback_verified'])
        self.assertEqual(final, NEW); self.assertNotEqual(final_inode, old_inode); self.assertEqual(backup, OLD)
        self.assertTrue(row['foreign_file_not_deleted'])

    def test_late_receipt_error_scoped_rollback_and_no_sealed_success(self):
        rc, row, final, inode, final_inode, _, _, rows = self.run_fixture('receipt')
        self.assertEqual(rc, 2); self.assertTrue(row['rollback_verified'])
        self.assertEqual((final, final_inode), (OLD, inode)); self.assertEqual(len(rows), 1)

    def test_kernel_return_fault_and_training_change_restore_only_asset(self):
        for fault in ('after_kernel', 'training'):
            with self.subTest(fault=fault):
                rc, row, final, inode, final_inode, _, _, _ = self.run_fixture(fault)
                self.assertEqual(rc, 2); self.assertTrue(row['rollback_verified'])
                self.assertEqual((final, final_inode), (OLD, inode))


if __name__ == '__main__':
    unittest.main()
