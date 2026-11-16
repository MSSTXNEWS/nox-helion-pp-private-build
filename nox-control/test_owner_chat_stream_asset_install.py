"""Finite filesystem/HTTP fixtures; never use native helpers or endpoints."""
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

import owner_chat_stream_asset_install as asset

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / 'coordination/onepass'
OLD = (PUBLIC / 'nox-v135-resonance-owner-bridge.js').read_bytes()
NEW = (PUBLIC / asset.CANDIDATE).read_bytes()


class FilesystemCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.root / 'site'; self.site.mkdir(mode=0o755)
        self.journal = self.root / 'private'; self.journal.mkdir(mode=0o700)
        self.target = self.site / asset.ASSET
        self.target.write_bytes(OLD); self.target.chmod(0o644)
        self.site_fd = asset.directory(self.site)
        self.journal_fd = asset.directory(self.journal)
        self.addCleanup(os.close, self.site_fd)
        self.addCleanup(os.close, self.journal_fd)
        old, before = asset.read_at(self.site_fd, asset.ASSET, expected=asset.OLD_SHA)
        asset.create(self.journal_fd, 'original.js', old)
        candidate = asset.create(self.journal_fd, 'exchange.js', NEW, before['mode'])
        self.prepared = {'before': before, 'candidate': candidate}

    def test_exchange_and_owned_rollback_preserve_original_inode_and_backup(self):
        latch = {}
        asset.publish(self.site_fd, self.journal_fd, self.prepared, latch)
        self.assertTrue(latch['exchange_attempted'])
        self.assertTrue(latch['exchange_returned'])
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual(self.target.stat().st_ino, self.prepared['candidate']['inode'])
        self.assertTrue(asset.restore_owned(self.site_fd, self.journal_fd, self.prepared))
        self.assertEqual(self.target.read_bytes(), OLD)
        self.assertEqual(self.target.stat().st_ino, self.prepared['before']['inode'])
        self.assertEqual((self.journal / 'original.js').read_bytes(), OLD)

    def test_foreign_same_content_inode_is_not_our_postimage(self):
        asset.publish(self.site_fd, self.journal_fd, self.prepared, {})
        foreign = self.site / 'foreign.js'; foreign.write_bytes(NEW); foreign.chmod(0o644)
        os.replace(foreign, self.target)
        inode = self.target.stat().st_ino
        with self.assertRaisesRegex(RuntimeError, 'INODE_CHANGED'):
            asset.restore_owned(self.site_fd, self.journal_fd, self.prepared)
        self.assertEqual(self.target.stat().st_ino, inode)
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual((self.journal / 'exchange.js').read_bytes(), OLD)

    def test_foreign_mode_is_not_reverted(self):
        asset.publish(self.site_fd, self.journal_fd, self.prepared, {})
        self.target.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'INODE_CHANGED'):
            asset.restore_owned(self.site_fd, self.journal_fd, self.prepared)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.journal / 'exchange.js').read_bytes(), OLD)

    def test_exception_after_kernel_exchange_is_recovered_from_actual_pair(self):
        real = asset.exchange; latch = {}
        def after_kernel(*args):
            real(*args)
            raise RuntimeError('HOLD_INJECTED_AFTER_KERNEL')
        with patch.object(asset, 'exchange', side_effect=after_kernel):
            with self.assertRaisesRegex(RuntimeError, 'AFTER_KERNEL'):
                asset.publish(self.site_fd, self.journal_fd, self.prepared, latch)
        self.assertTrue(latch['exchange_attempted'])
        self.assertNotIn('exchange_returned', latch)
        self.assertTrue(asset.restore_owned(self.site_fd, self.journal_fd, self.prepared))
        self.assertEqual(self.target.stat().st_ino, self.prepared['before']['inode'])

    def test_fsync_failure_after_exchange_still_has_ownership_latch(self):
        latch = {}
        with patch.object(asset.os, 'fsync', side_effect=OSError('private error')):
            with self.assertRaises(OSError):
                asset.publish(self.site_fd, self.journal_fd, self.prepared, latch)
        self.assertTrue(latch['exchange_returned'])
        self.assertTrue(asset.restore_owned(self.site_fd, self.journal_fd, self.prepared))

    def test_foreign_destination_in_check_exchange_gap_is_preserved(self):
        real = asset.exchange; calls = 0
        foreign = self.site / 'foreign.js'; foreign.write_bytes(b'foreign owner data'); foreign.chmod(0o644)
        foreign_inode = foreign.stat().st_ino
        old_private = self.site / 'prior-owned.js'
        def race(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                os.rename(self.target, old_private)
                os.rename(foreign, self.target)
            return real(*args)
        latch = {}
        with patch.object(asset, 'exchange', side_effect=race):
            with self.assertRaisesRegex(RuntimeError, 'FOREIGN_RESTORED'):
                asset.publish(self.site_fd, self.journal_fd, self.prepared, latch)
        self.assertEqual(calls, 2)
        self.assertTrue(latch['foreign_namespace_restored'])
        self.assertEqual(self.target.stat().st_ino, foreign_inode)
        self.assertEqual(self.target.read_bytes(), b'foreign owner data')
        self.assertEqual(old_private.read_bytes(), OLD)
        self.assertEqual((self.journal / 'exchange.js').read_bytes(), NEW)

    def test_preexisting_candidate_or_unknown_bytes_cannot_be_fresh_preimage(self):
        for data in (NEW, b'unknown'):
            self.target.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError, 'FILE_SHA'):
                asset.read_at(self.site_fd, asset.ASSET, expected=asset.OLD_SHA)

    def test_private_readback_corruption_stops_before_publish(self):
        real = asset.read_at
        def corrupt(parent, name, *args, **kwargs):
            if name == 'prepared.json':
                (self.journal / name).write_bytes(b'foreign')
            return real(parent, name, *args, **kwargs)
        with patch.object(asset, 'read_at', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'FILE_SHA'):
                asset.private_json(self.journal_fd, 'prepared.json', self.prepared)
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_failed_final_receipt_rolls_back_without_replacing_failed_receipt(self):
        asset.publish(self.site_fd, self.journal_fd, self.prepared, {})
        row = {'state': asset.ACCEPTED, 'success': True}
        real = asset.private_json
        def fail_after_write(parent, name, value):
            result = real(parent, name, value)
            if name == 'receipt.json':
                raise RuntimeError('HOLD_INJECTED_RECEIPT_READBACK')
            return result
        with patch.object(asset, 'private_json', side_effect=fail_after_write):
            sealed = asset.seal_result(self.journal_fd, row,
                lambda: asset.restore_owned(self.site_fd, self.journal_fd, self.prepared))
        self.assertIsNone(sealed)
        self.assertFalse(row['success'])
        self.assertTrue(row['rollback_verified'])
        self.assertEqual(self.target.read_bytes(), OLD)
        self.assertTrue(json.loads((self.journal / 'receipt.json').read_bytes())['success'])
        self.assertFalse(json.loads((self.journal / 'receipt_failure.json').read_bytes())['success'])


class MainCase(unittest.TestCase):
    def run_main(self, *, fail_after_http=False, stop_before_publish=False):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp); state = root / 'state'; state.mkdir(mode=0o700)
            site = root / 'site'; site.mkdir(mode=0o755)
            target = site / asset.ASSET; target.write_bytes(OLD); target.chmod(0o644)
            maintenance = state / 'owner_maintenance.lock'; maintenance.touch(mode=0o600)
            area = state / 'owner_chat_stream_installs'
            client = types.SimpleNamespace(cookie='private-test-cookie', close=lambda: None)
            auth = types.SimpleNamespace(OwnerClient=types.SimpleNamespace(authenticate=lambda: client))
            before = {'boot_id': 'boot-fixture', 'model': {'pid': 7637},
                      'proxy': {'pid': 8080}, 'trainer': {'state': 'RUNNING', 'pid': 22}}
            def request(host, path, cookie=None, maximum=262144):
                self.assertEqual(host, '192.0.2.10')
                if path == asset.PAGE:
                    return 200, ('<script src="' + asset.URL + '"></script>').encode()
                self.assertEqual(path, asset.URL)
                if cookie is None:
                    return 401, b''
                self.assertEqual(cookie, client.cookie)
                data = target.read_bytes()
                if fail_after_http and data == NEW:
                    return 200, b'wrong public body'
                return 200, data
            for name, value in {'ROOT':root, 'STATE':state, 'SITE':site, 'AREA':area}.items():
                stack.enter_context(patch.object(asset, name, value))
            stack.enter_context(patch.dict(os.environ, {
                'NOX_OWNER_REQUEST_ID':'123456', 'NOX_OWNER_SOURCE_SHA':'a' * 40}))
            # The filesystem fixture is owned by the local test UID. Only the
            # production entry's root-launch check is bypassed; every actual
            # file/directory UID, mode and named-inode check still runs.
            real_require = asset.require
            stack.enter_context(patch.object(asset, 'require', side_effect=lambda ok, code:
                real_require(True if code == 'ROOT_REQUIRED' else ok, code)))
            stack.enter_context(patch.object(asset, 'bundle_sources', return_value=(NEW, auth, object())))
            stack.enter_context(patch.object(asset, 'source_guards', return_value={'protected':'exact'}))
            stack.enter_context(patch.object(asset, 'identities', return_value=before))
            stack.enter_context(patch.object(asset, 'health', return_value={'8080':200, '8081':200, '8082':200}))
            stack.enter_context(patch.object(asset, 'local_address', return_value='192.0.2.10'))
            stack.enter_context(patch.object(asset, 'http_get', side_effect=request))
            stack.enter_context(patch.object(asset.signal, 'setitimer'))
            if stop_before_publish:
                real = asset.private_json
                def add_stop(parent, name, value):
                    row = real(parent, name, value)
                    if name == 'exchange_intent.json':
                        (root / 'STOP').touch()
                    return row
                stack.enter_context(patch.object(asset, 'private_json', side_effect=add_stop))
            output = io.StringIO()
            with redirect_stdout(output):
                rc = asset.main()
            result = json.loads((area / '123456/receipt.json').read_bytes())
            return rc, result, target.read_bytes(), output.getvalue()

    def test_one_asset_success_is_http_only_and_sealed(self):
        rc, row, actual, output = self.run_main()
        self.assertEqual(rc, 0); self.assertTrue(row['success']); self.assertEqual(actual, NEW)
        self.assertEqual(row['http_after']['sha256'], asset.NEW_SHA)
        self.assertFalse(row['browser_acceptance_verified'])
        self.assertFalse(row['performance_change_verified'])
        self.assertFalse(row['training_control_performed'])
        self.assertIn('chat_stream_asset_context', output)
        self.assertNotIn('private-test-cookie', output)

    def test_http_verification_failure_rolls_back_only_owned_asset(self):
        rc, row, actual, output = self.run_main(fail_after_http=True)
        self.assertEqual(rc, 2); self.assertFalse(row['success'])
        self.assertTrue(row['rollback_verified']); self.assertEqual(actual, OLD)
        self.assertEqual(row['reason'], 'HOLD_STREAM_ASSET_HTTP_ASSET')

    def test_global_stop_after_durable_intent_prevents_namespace_change(self):
        rc, row, actual, output = self.run_main(stop_before_publish=True)
        self.assertEqual(rc, 2); self.assertFalse(row['success'])
        self.assertFalse(row['rollback_requested']); self.assertEqual(actual, OLD)
        self.assertEqual(row['reason'], 'HOLD_STREAM_ASSET_OWNER_STOP')


class ScopeCase(unittest.TestCase):
    def test_exact_three_file_bundle_has_definition_only_helpers(self):
        bundle = {}
        for name, pin in asset.PINS.items():
            raw = (PUBLIC / name if name == asset.CANDIDATE else HERE / name).read_bytes()
            self.assertEqual(asset.digest(raw), pin)
            bundle[name] = base64.b64encode(raw).decode()
        with patch.object(asset, 'BUNDLE', bundle):
            data, auth, helper = asset.bundle_sources()
        self.assertEqual(data, NEW)
        self.assertTrue(callable(auth.OwnerClient.authenticate))
        self.assertTrue(callable(helper.process))
        self.assertEqual(len(OLD), asset.OLD_BYTES)
        self.assertEqual(len(NEW), asset.NEW_BYTES)
        bundle[asset.CANDIDATE] = base64.b64encode(OLD).decode()
        with patch.object(asset, 'BUNDLE', bundle):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                asset.bundle_sources()

    def test_shared_maintenance_allows_guard_readers_but_excludes_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lease'; path.touch(mode=0o600)
            with asset.lease(path, shared=True):
                with asset.lease(path, shared=True):
                    pass
                with self.assertRaises(BlockingIOError):
                    with asset.lease(path):
                        self.fail('exclusive owner should wait')

    def test_http_route_and_error_output_are_bounded(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP_PATH'):
            asset.http_get('192.0.2.1', '/arbitrary')
        with self.assertRaisesRegex(RuntimeError, 'HTTP_BOUND'):
            asset.http_get('192.0.2.1', asset.URL, maximum=10 ** 9)
        self.assertEqual(asset.safe(OSError('secret-url-and-content')), 'HOLD_STREAM_ASSET_OSERROR')


if __name__ == '__main__':
    unittest.main()
