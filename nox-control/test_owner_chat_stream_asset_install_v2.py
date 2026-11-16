"""Exact permission transition + existing one-asset rollback; local fixtures."""
import ast
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_chat_stream_asset_install_v2 as asset
import test_owner_chat_stream_asset_install as original_tests

HERE = Path(__file__).resolve().parent
OLD, NEW = original_tests.OLD, original_tests.NEW


class OriginalExchangeRegression(original_tests.FilesystemCase):
    def setUp(self):
        self.binding = patch.object(original_tests, 'asset', asset)
        self.binding.start(); self.addCleanup(self.binding.stop)
        super().setUp()


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.site = self.root / 'site'; self.pc = self.site / 'pc'
        self.pc.mkdir(parents=True); self.site.chmod(0o775); self.pc.chmod(0o775)
        self.expected = {p: asset.permission_identity(p.stat()) for p in (self.site, self.pc)}
        self.stack.enter_context(patch.object(asset, 'SITE', self.site))
        self.stack.enter_context(patch.object(asset, 'DIRECTORY_PREIMAGES', self.expected))
        self.stack.enter_context(patch.object(asset, 'stopped', return_value=False))
        self.fds = {p: asset.observed_directory(p) for p in self.expected}
        for fd in self.fds.values(): self.stack.callback(os.close, fd)
        self.changes = {}

    def harden(self):
        for path, fd in self.fds.items(): asset.protect_directory(path, fd, self.changes)

    def undo(self):
        row = {}
        result = asset.rollback_transaction(self.fds[self.site], None, None, {}, self.fds, self.changes, row)
        return result, row

    def test_two_exact_inodes_harden_and_restore_without_owner_change(self):
        self.harden()
        for path in self.expected:
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
            self.assertEqual(path.stat().st_ino, self.expected[path]['inode'])
        result, row = self.undo(); self.assertTrue(result)
        self.assertTrue(row['directory_permission_rollback_verified'])
        for path in self.expected:
            self.assertEqual(asset.permission_identity(path.stat()), self.expected[path])

    def test_failure_after_chmod_before_fsync_retains_rollback_intent(self):
        with patch.object(asset.os, 'fsync', side_effect=OSError('private failure')):
            with self.assertRaises(OSError):
                asset.protect_directory(self.site, self.fds[self.site], self.changes)
        self.assertTrue(self.changes[self.site]['attempted'])
        self.assertEqual(self.site.stat().st_mode & 0o777, 0o755)
        self.assertTrue(self.undo()[0]); self.assertEqual(self.site.stat().st_mode & 0o777, 0o775)

    def test_foreign_mode_is_classified_before_any_compensating_chmod(self):
        self.harden(); self.pc.chmod(0o700)
        with patch.object(asset.os, 'fchmod', side_effect=AssertionError('must not mutate')):
            with self.assertRaisesRegex(RuntimeError, 'PERMISSION_ROLLBACK_FOREIGN_MODE'):
                self.undo()
        self.assertEqual(self.site.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.pc.stat().st_mode & 0o777, 0o700)

    def test_named_directory_replacement_is_preserved_without_chmod(self):
        self.harden(); old = self.root / 'owned-before'; self.site.rename(old)
        self.site.mkdir(mode=0o755); (self.site / 'pc').mkdir(mode=0o755)
        foreign = self.site.stat().st_ino
        with patch.object(asset.os, 'fchmod', side_effect=AssertionError('must not mutate')):
            with self.assertRaisesRegex(RuntimeError, 'PERMISSION_'):
                self.undo()
        self.assertEqual(self.site.stat().st_ino, foreign)
        self.assertEqual(old.stat().st_mode & 0o777, 0o755)

    def test_changed_initial_mode_or_inode_is_not_a_generic_exception(self):
        self.site.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, 'PERMISSION_PREIMAGE'):
            asset.observed_directory(self.site)
        with self.assertRaisesRegex(RuntimeError, 'PERMISSION_PATH_SCOPE'):
            asset.fixed_directory(self.root)


class IntegratedTests(unittest.TestCase):
    def run_main(self, failure=None):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp); state = root / 'state'; state.mkdir(mode=0o700)
            site = root / 'site'; pc = site / 'pc'; pc.mkdir(parents=True)
            site.chmod(0o775); pc.chmod(0o775)
            expected = {p: asset.permission_identity(p.stat()) for p in (site, pc)}
            target = site / asset.ASSET; target.write_bytes(OLD); target.chmod(0o644)
            (state / 'owner_maintenance.lock').touch(mode=0o600)
            area = state / 'owner_chat_stream_installs'
            for name, value in {'ROOT':root, 'STATE':state, 'SITE':site, 'AREA':area,
                                'DIRECTORY_PREIMAGES':expected}.items():
                stack.enter_context(patch.object(asset, name, value))
            stack.enter_context(patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID':'123456', 'NOX_OWNER_SOURCE_SHA':'a' * 40}))
            real_require = asset.require
            stack.enter_context(patch.object(asset, 'require', side_effect=lambda ok, code:
                real_require(True if code == 'ROOT_REQUIRED' else ok, code)))
            client = types.SimpleNamespace(cookie='private-cookie', close=lambda: None)
            auth = types.SimpleNamespace(OwnerClient=types.SimpleNamespace(authenticate=lambda: client))
            stack.enter_context(patch.object(asset, 'bundle_sources', return_value=(NEW, auth, object())))
            stack.enter_context(patch.object(asset, 'source_guards_observed', return_value={'fixed':'exact'}))
            stack.enter_context(patch.object(asset, 'source_guards', return_value={'fixed':'exact'}))
            process = {'boot_id':'fixture', 'model':{'pid':7637}, 'proxy':{'pid':123}, 'trainer':{'state':'FATAL','pid':None}}
            stack.enter_context(patch.object(asset, 'identities', return_value=process))
            stack.enter_context(patch.object(asset, 'health', return_value={'8080':200,'8081':200,'8082':200}))
            stack.enter_context(patch.object(asset, 'local_address', return_value='192.0.2.10'))
            stack.enter_context(patch.object(asset.signal, 'setitimer'))
            def request(host, path, cookie=None, maximum=262144):
                if path == asset.PAGE:
                    return 200, ('<script src="' + asset.URL + '"></script>').encode()
                if cookie is None:return 401, b''
                raw = target.read_bytes()
                if failure == 'http' and raw == NEW:return 200, b'foreign response'
                return 200, raw
            stack.enter_context(patch.object(asset, 'http_get', side_effect=request))
            real_json = asset.private_json
            def private_json(fd, name, row):
                if failure == 'intent' and name == 'directory_permission_intent.json':
                    raise RuntimeError('HOLD_INTENT_READBACK')
                result = real_json(fd, name, row)
                if failure == 'receipt' and name == 'receipt.json':
                    raise RuntimeError('HOLD_FINAL_READBACK')
                return result
            stack.enter_context(patch.object(asset, 'private_json', side_effect=private_json))
            output = io.StringIO()
            with redirect_stdout(output): rc = asset.main()
            rows = [json.loads(line.split('=',1)[1]) for line in output.getvalue().splitlines()
                    if line.startswith('NOX_MAINT_REPAIR=')]
            record = next(row['data'] for row in rows if row['kind'] == 'chat_stream_asset_install')
            modes = [path.stat().st_mode & 0o777 for path in (site,pc)]
            journal = area / '123456'
            intent = json.loads((journal / 'directory_permission_intent.json').read_bytes()) if (journal / 'directory_permission_intent.json').exists() else None
            return rc, record, modes, target.read_bytes(), rows, intent

    def test_success_hardens_two_dirs_then_installs_exact_asset(self):
        rc, row, modes, body, rows, intent = self.run_main()
        self.assertEqual(rc,0); self.assertTrue(row['success']); self.assertEqual(body,NEW)
        self.assertEqual(modes,[0o755,0o755]); self.assertTrue(row['directory_permissions_hardened'])
        self.assertEqual(intent['after_mode'],0o755)
        self.assertEqual({v['mode'] for v in intent['before'].values()},{0o775})
        self.assertFalse(row['training_control_performed']); self.assertFalse(row['proxy_restarted'])

    def test_bad_permission_intent_prevents_any_chmod_or_asset_change(self):
        rc, row, modes, body, _, intent = self.run_main('intent')
        self.assertEqual(rc,2); self.assertEqual(modes,[0o775,0o775]); self.assertEqual(body,OLD)
        self.assertFalse(row['rollback_requested']); self.assertIsNone(intent)

    def test_http_failure_restores_source_pair_and_both_modes(self):
        rc, row, modes, body, _, _ = self.run_main('http')
        self.assertEqual(rc,2); self.assertEqual(modes,[0o775,0o775]); self.assertEqual(body,OLD)
        self.assertTrue(row['rollback_verified']); self.assertTrue(row['directory_permission_rollback_verified'])

    def test_late_receipt_failure_restores_source_modes_without_sealed_context(self):
        rc, row, modes, body, rows, _ = self.run_main('receipt')
        self.assertEqual(rc,2); self.assertEqual(modes,[0o775,0o775]); self.assertEqual(body,OLD)
        self.assertTrue(row['rollback_verified']); self.assertFalse(row['success'])
        self.assertFalse(any(row['kind']=='chat_stream_asset_context' for row in rows))


class SourceProofTests(unittest.TestCase):
    def test_preserved00fe_is_exact_reviewed_cold_patch_of62ad(self):
        raw = (HERE / 'owner_builder_cold_storage_entry.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'77199afa4b08feda5e3734255c7899d00194cbda23458792cc26c02657bf9df6')
        tree = ast.parse(raw); fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='patch_js')
        scope = {'sha':asset.digest,'require':asset.require,
                 'OLD_JS':'62ad2c08382ee6ef6cec3c8eb0ba4598c4c09037f442ce83a04c0344d686525a'}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<cold-js-transform>','exec'),scope)
        output = scope['patch_js']((HERE/'owner-chat-ui.js').read_bytes())
        self.assertEqual(len(output),17962)
        self.assertEqual(asset.digest(output),asset.PROTECTED[asset.SITE/'owner-chat-ui.js'])

    def test_original_strict_guards_exchange_http_and_identity_functions_are_unchanged(self):
        original = (HERE / 'owner_chat_stream_asset_install.py').read_bytes()
        self.assertEqual(asset.digest(original),'6c4b9453cd0ea4a948dda521f14c21f5d956ad865f66ed027fe2bc642beb3641')
        old = {n.name:ast.dump(n) for n in ast.parse(original).body if isinstance(n,ast.FunctionDef)}
        new = {n.name:ast.dump(n) for n in ast.parse(Path(asset.__file__).read_bytes()).body if isinstance(n,ast.FunctionDef)}
        for name in ('directory','read_at','create','private_json','exchange','verify_pair','checked_exchange',
                     'publish','rollback','restore_owned','lease','identities','health','http_get','http_asset','source_guards'):
            self.assertEqual(new[name],old[name],name)


if __name__ == '__main__':
    unittest.main()
