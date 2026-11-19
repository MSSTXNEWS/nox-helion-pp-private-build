"""Local filesystem fixtures only: no native endpoints or service actions."""
import ast
import base64
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
import stat
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_chat_markdown_asset_install_v2 as w

HERE = Path(__file__).resolve().parent
JS = HERE.parent / 'coordination/onepass' / w.CANDIDATE
BUNDLE = {name: base64.b64encode((JS if name == w.CANDIDATE else HERE / name).read_bytes()).decode()
          for name in w.DEPENDENCIES}
OLD = b'original-v24-chat-fixture'
NEW = JS.read_bytes()


class MarkdownInstallerV2Tests(unittest.TestCase):
    def library(self):
        with patch.object(w, 'BUNDLE', BUNDLE):
            return w.prepared_library()[0]

    def run_fixture(self, fail=None):
        b = self.library(); output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary); state = root / 'state'; state.mkdir(mode=0o700)
            site_root = root / 'site'; site_root.mkdir(mode=0o755)
            pc = site_root / 'pc'; pc.mkdir(mode=0o755)
            site = pc / 'v24'; site.mkdir(mode=0o775); site.chmod(0o775)
            target = site / 'nox-v24-chat.js'; target.write_bytes(OLD); target.chmod(0o644)
            original_inode = target.stat().st_ino
            (state / 'owner_maintenance.lock').touch(mode=0o600)
            for name, value in {'ROOT': root, 'STATE': state, 'SITE': site,
                'AREA': state / 'owner_chat_markdown_asset_installs_v2', 'OLD_SHA': b.digest(OLD), 'OLD_BYTES': len(OLD)}.items():
                stack.enter_context(patch.object(b, name, value))
            stack.enter_context(patch.object(w, 'OLD_SHA', b.digest(OLD)))
            stack.enter_context(patch.object(w, 'OLD_BYTES', len(OLD)))
            directory_preimage = b.permission_identity(site.stat())
            asset_preimage = {key: b.identity(target.stat())[key] for key in w.ASSET_PREIMAGE}
            stack.enter_context(patch.object(w, 'V24_DIRECTORY_PREIMAGE', directory_preimage))
            stack.enter_context(patch.object(w, 'ASSET_PREIMAGE', asset_preimage))
            stack.enter_context(patch.object(b, 'DIRECTORY_PREIMAGES', {site: dict(directory_preimage)}))
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
            for name in ('main', 'permission_intent'):
                stack.enter_context(patch.object(b, name, side_effect=AssertionError('old workflow must not run')))
            def training(*_):
                snapshots.append(True)
                return {'state': 'FATAL', 'pid': None, 'flag': 'changed' if fail == 'training' and len(snapshots) == 3 else 'same'}
            stack.enter_context(patch.object(w, 'training_snapshot', side_effect=training))
            def http(host, path, cookie=None, maximum=262144):
                self.assertEqual(host, '192.0.2.1')
                if path == b.PAGE:
                    return 200, b'<script defer src="./v24/nox-v24-chat.js"></script>'
                self.assertEqual(path, '/nox-web-v29/pc/v24/nox-v24-chat.js')
                if cookie is None:
                    return 401, b''
                self.assertEqual(cookie, client.cookie)
                current = target.read_bytes()
                if current == NEW and fail == 'http':
                    return 200, b'incorrect bytes'
                if current == NEW and fail == 'foreign_mode':
                    site.chmod(0o700)
                    return 200, b'incorrect bytes'
                if current == NEW and fail == 'foreign':
                    other = site / 'other.js'; other.write_bytes(NEW); other.chmod(0o644)
                    os.replace(other, target)
                return 200, current
            stack.enter_context(patch.object(b, 'http_get', side_effect=http))
            if fail == 'preimage':
                target.write_bytes(b'foreign preimage')
            if fail == 'directory':
                site.chmod(0o777)
            if fail == 'parent_directory':
                pc.chmod(0o775)
            if fail == 'directory_inode':
                b.DIRECTORY_PREIMAGES[site]['inode'] += 1
            if fail == 'file_inode':
                other = site / 'replacement.js'; other.write_bytes(OLD); other.chmod(0o644)
                os.replace(other, target)
            if fail == 'before_mode_source':
                real_intent = w.permission_intent
                def changed_after_intent(*args):
                    value = real_intent(*args); target.write_bytes(b'foreign-after-intent'); return value
                stack.enter_context(patch.object(w, 'permission_intent', side_effect=changed_after_intent))
            if fail == 'stop_after_mode':
                real_protect = b.protect_directory
                def stopped_after_protect(*args):
                    real_protect(*args); (root / 'STOP').write_bytes(b'foreign-owner-stop')
                stack.enter_context(patch.object(b, 'protect_directory', side_effect=stopped_after_protect))
            real_chmod = os.fchmod; permission_events = []
            def checked_chmod(fd, mode):
                info = os.fstat(fd)
                if stat.S_ISDIR(info.st_mode):
                    self.assertEqual((info.st_dev, info.st_ino), (directory_preimage['device'], directory_preimage['inode']))
                    self.assertIn(mode, (0o755, 0o775))
                    journal = b.AREA / '123'
                    intent_path = journal / 'directory_permission_intent.json'
                    intent = json.loads(intent_path.read_bytes())
                    self.assertEqual(intent_path.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(intent['before'], {'SITE_PC_V24': directory_preimage})
                    self.assertEqual(intent['owner_metadata_receipt_sha256'], w.METADATA_RECEIPT_SHA)
                    self.assertEqual((journal / 'original.js').read_bytes(), OLD)
                    permission_events.append(mode)
                    real_chmod(fd, mode)
                    if fail == 'after_chmod' and mode == 0o755:
                        raise RuntimeError('HOLD_FIXTURE_AFTER_DIRECTORY_CHMOD')
                    return
                return real_chmod(fd, mode)
            stack.enter_context(patch.object(os, 'fchmod', side_effect=checked_chmod))
            if fail == 'permission_fsync':
                real_fsync = os.fsync; faults = []
                def fsync_fault(fd):
                    info = os.fstat(fd)
                    if (not faults and stat.S_ISDIR(info.st_mode) and info.st_ino == directory_preimage['inode']
                            and stat.S_IMODE(info.st_mode) == 0o755):
                        faults.append(True); raise RuntimeError('HOLD_FIXTURE_DIRECTORY_FSYNC')
                    return real_fsync(fd)
                stack.enter_context(patch.object(os, 'fsync', side_effect=fsync_fault))
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
            expected_mode = 0o755 if fail in (None, 'foreign') else (0o777 if fail == 'directory' else 0o700 if fail == 'foreign_mode' else 0o775)
            self.assertEqual(site.stat().st_mode & 0o777, expected_mode)
            self.last_permission_events = permission_events
            self.last_directory_mode = site.stat().st_mode & 0o777
            self.last_stop_bytes = (root / 'STOP').read_bytes() if (root / 'STOP').exists() else None
            self.assertEqual(pc.stat().st_mode & 0o777, 0o775 if fail == 'parent_directory' else 0o755)
            self.assertEqual(site_root.stat().st_mode & 0o777, 0o755)
            return rc, result, final, original_inode, final_inode, backup, auth_calls, rows

    def test_actual_bundle_pins_paths_and_reused_rollback_functions(self):
        b = self.library()
        self.assertEqual(str(b.SITE), '/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/v24')
        self.assertEqual(b.ASSET, 'nox-v24-chat.js')
        self.assertEqual(len(NEW), 33070)
        self.assertEqual(b.digest(NEW), w.NEW_SHA)
        self.assertEqual(b.digest((HERE / w.BASE_NAME).read_bytes()), w.BASE_SHA)
        self.assertEqual(b.PROTECTED[b.SITE.parent.parent / 'nox-v135-resonance-owner-bridge.js'], w.COALESCED_SHA)
        self.assertEqual(b.PROTECTED[b.SITE.parent / 'workspace.js'], w.WORKSPACE_SHA)
        tree = ast.parse(Path(w.__file__).read_text())
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertFalse(calls & {'b.main', 'b.permission_intent', 'os.chmod', 'os.fchmod',
                                  'helper.command', 'helper.run', 'subprocess.run', 'subprocess.Popen'})

    def test_missing_or_changed_bundle_fails_before_native_action(self):
        for bundle in ({}, {**BUNDLE, w.BASE_NAME: base64.b64encode(b'foreign').decode()}):
            with patch.object(w, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_'):
                w.prepared_library()

    def test_success_is_http_proof_not_browser_behavior(self):
        rc, row, final, _, _, backup, _, rows = self.run_fixture()
        self.assertEqual(rc, 0); self.assertTrue(row['success']); self.assertEqual(final, NEW)
        self.assertEqual(backup, OLD); self.assertFalse(row['browser_acceptance_verified'])
        self.assertTrue(row['directory_permissions_modified']); self.assertFalse(row['proxy_restarted'])
        self.assertEqual(self.last_permission_events, [0o755]); self.assertEqual(self.last_directory_mode, 0o755)
        self.assertFalse(row['parent_directory_permissions_modified'])
        self.assertFalse(row['markdown_end_to_end_verified']); self.assertFalse(row['history_writes_performed'])
        self.assertEqual((row['application_posts_sent'], row['generation_requests_sent'], row['dialogs_created']), (0, 0, 0))
        self.assertTrue(row['training_sources_flags_and_observed_processes_preserved'])
        self.assertEqual(rows[1]['kind'], 'chat_markdown_asset_context_v2')

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


    def test_unknown_writable_target_or_parent_directory_fails_before_auth(self):
        for fault in ('directory', 'parent_directory'):
            with self.subTest(fault=fault):
                rc, row, final, inode, final_inode, backup, auth, _ = self.run_fixture(fault)
                self.assertEqual(rc, 2); self.assertFalse(row['success'])
                self.assertEqual((final, final_inode), (OLD, inode))
                self.assertIsNone(backup); self.assertEqual(auth, [])
                self.assertFalse(row['directory_permissions_modified'])

    def test_actual_script_reference_rejects_comments_aliases_and_duplicates(self):
        tag = b'<script defer src="./v24/nox-v24-chat.js"></script>'
        self.assertTrue(w.page_reference(tag))
        for page in (b'', b'<!--' + tag + b'-->', tag + tag,
                     tag.replace(b'./v24/', b'/nox-web-v29/pc/v24/'),
                     tag.replace(b'.js"', b'.js?version=1"'),
                     tag.replace(b'.js"', b'.js#fragment"'),
                     tag.replace(b' src=', b' data-src='),
                     tag.replace(b' src=', b' src="foreign.js" src=')):
            with self.subTest(page=page):
                self.assertFalse(w.page_reference(page))

    def test_dynamic_training_snapshot_preserves_flags_and_process_identity(self):
        b = self.library()
        with tempfile.TemporaryDirectory() as temporary, patch.object(b, 'ROOT', Path(temporary)):
            for name in ('state/owner_training_admission.json', 'scripts/run_train_volta_t866u.sh',
                         'config/owner_training_status.json', 'scripts/nox_admin.py',
                         'state/TRAIN_HOLD.flag', 'state/TRAIN_PAUSE_REQUEST.flag'):
                path = b.ROOT / name; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                path.write_bytes(b'preserved-' + name.encode()); path.chmod(0o600)
            process = {'pid': 17, 'ppid': 1, 'pgrp': 17, 'starttime': '100', 'cuda': '1',
                       'argv': ['python', 'fixed-student'], 'service': 'nox-train-volta-t866u', 'state': 'S'}
            helper = types.SimpleNamespace(service_state=lambda name: {'state': 'RUNNING', 'pid': 17},
                                           process_table=lambda: {17: dict(process)})
            before = w.training_snapshot(b, helper)
            self.assertEqual(before['state'], 'RUNNING')
            process['starttime'] = '101'
            self.assertNotEqual(w.training_snapshot(b, helper), before)
            process['starttime'] = '100'
            (b.ROOT / 'state/TRAIN_HOLD.flag').write_bytes(b'foreign')
            self.assertNotEqual(w.training_snapshot(b, helper), before)
            helper.service_state = lambda name: {'state': 'FATAL', 'pid': None}
            with self.assertRaisesRegex(RuntimeError, 'TRAINER_UNEXPECTED'):
                w.training_snapshot(b, helper)

    def test_protected_coalesced_and_workspace_hash_changes_fail_closed(self):
        b = self.library()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary); site = root / 'site'; site.mkdir(mode=0o755)
            pc = site / 'pc'; pc.mkdir(mode=0o755)
            bridge = site / 'nox-v135-resonance-owner-bridge.js'; bridge.write_bytes(b'bridge'); bridge.chmod(0o644)
            workspace = pc / 'workspace.js'; workspace.write_bytes(b'workspace'); workspace.chmod(0o644)
            stack.enter_context(patch.object(b, 'ROOT', root))
            stack.enter_context(patch.object(b, 'PROTECTED', {bridge: b.digest(b'bridge'), workspace: b.digest(b'workspace')}))
            self.assertEqual(len(b.source_guards()), 2)
            for path in (bridge, workspace):
                original = path.read_bytes(); path.write_bytes(b'foreign')
                with self.assertRaisesRegex(RuntimeError, 'PROTECTED_SOURCE'):
                    b.source_guards()
                path.write_bytes(original)


    def test_exact_observed_native_directory_and_asset_metadata_constants(self):
        b = self.library()
        self.assertEqual(w.V24_DIRECTORY_PREIMAGE, {'device': 39, 'inode': 2223497631, 'uid': 0, 'gid': 0, 'mode': 0o775})
        self.assertEqual(b.DIRECTORY_PREIMAGES, {b.SITE: w.V24_DIRECTORY_PREIMAGE})
        self.assertEqual(w.ASSET_PREIMAGE, {'device': 39, 'inode': 2223497633, 'uid': 0, 'gid': 0,
                                          'mode': 0o644, 'nlink': 1, 'bytes': 32074, 'regular': True})
        self.assertEqual(w.METADATA_RECEIPT_SHA, '7897e9e53cb3a57aed35d490fab0da1be02c2867c6e60f57adb1b4b0df50daab')

    def test_foreign_directory_or_file_inode_rejected_before_auth_or_permission(self):
        for fault in ('directory_inode', 'file_inode'):
            with self.subTest(fault=fault):
                rc, row, final, _, _, backup, auth, _ = self.run_fixture(fault)
                self.assertEqual(rc, 2); self.assertFalse(row['success'])
                self.assertEqual(final, OLD); self.assertIsNone(backup); self.assertEqual(auth, [])
                self.assertEqual(self.last_permission_events, [])

    def test_full_preimage_rechecked_after_intent_before_permission_syscall(self):
        rc, row, final, _, _, backup, _, _ = self.run_fixture('before_mode_source')
        self.assertEqual(rc, 2); self.assertFalse(row['success'])
        self.assertEqual(final, b'foreign-after-intent'); self.assertEqual(backup, OLD)
        self.assertEqual(self.last_permission_events, [])
        self.assertFalse(row['directory_permission_change_attempted'])

    def test_partial_chmod_or_fsync_failure_restores_only_owned_mode(self):
        for fault in ('after_chmod', 'permission_fsync'):
            with self.subTest(fault=fault):
                rc, row, final, inode, final_inode, backup, _, _ = self.run_fixture(fault)
                self.assertEqual(rc, 2); self.assertTrue(row['rollback_verified'])
                self.assertEqual((final, final_inode, backup), (OLD, inode, OLD))
                self.assertEqual(self.last_permission_events, [0o755, 0o775])
                self.assertTrue(row['directory_permission_change_attempted'])
                self.assertIsNone(row['directory_permissions_modified'])
                self.assertTrue(row['directory_permission_rollback_verified'])

    def test_foreign_stop_after_hardening_remains_and_own_mode_is_restored(self):
        rc, row, final, inode, final_inode, _, _, _ = self.run_fixture('stop_after_mode')
        self.assertEqual(rc, 2); self.assertTrue(row['rollback_verified'])
        self.assertEqual((final, final_inode), (OLD, inode))
        self.assertEqual(self.last_permission_events, [0o755, 0o775])
        self.assertEqual(self.last_stop_bytes, b'foreign-owner-stop')

    def test_foreign_directory_mode_prevents_any_asset_or_permission_undo(self):
        rc, row, final, _, _, backup, _, _ = self.run_fixture('foreign_mode')
        self.assertEqual(rc, 2); self.assertFalse(row['rollback_verified'])
        self.assertEqual(final, NEW); self.assertEqual(backup, OLD)
        self.assertEqual(self.last_permission_events, [0o755]); self.assertEqual(self.last_directory_mode, 0o700)
        self.assertTrue(row['foreign_file_not_deleted'])


if __name__ == '__main__':
    unittest.main()
