"""Real TempFS file/lock/rename/fsync contracts; no native NOX execution."""
import ast
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import native_post8098_headroom_install as install


HERE = Path(__file__).resolve().parent


class SourceInstallContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nox_source_install_contract_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'nox'
        (self.root / 'state').mkdir(parents=True)
        (self.root / 'scripts').mkdir()
        self.target = self.root / 'scripts' / install.TARGET
        source = Path(os.environ.get('NOX_POST8098_BEFORE',
                          str(HERE / 'post8098_chain_exec09.before.sh'))).read_bytes()
        self.assertEqual((len(source), hashlib.sha256(source).hexdigest()),
                         (install.BEFORE['bytes'], install.BEFORE['sha256']))
        self.assertEqual(install.BEFORE['dev'], 36)
        self.assertEqual(install.BEFORE['ino'], 1152408707)
        self.assertEqual(install.BEFORE['mtime_ns'], 1794895746508029718)
        self.assertEqual(install.LOCK_PIN, {'dev': 36, 'ino': 59886214})
        self.target.write_bytes(source); self.target.chmod(0o775)
        self.original = source
        self.lock = self.root / 'state/owner_maintenance.lock'
        self.lock.write_bytes(b''); self.lock.chmod(0o600)
        self.training_hold = self.root / 'state/TRAIN_HOLD.flag'
        self.training_hold.write_bytes(b'KEEP_OWNER_HOLD\n')
        self.counter = self.root / 'state/chat_activity.json'
        self.counter.write_bytes(b'{"untouched":true}\n')
        source_pin = {**install.metadata(self.target.stat()), 'sha256': install.BEFORE['sha256']}
        lock_info = self.lock.stat()
        for name, value in [('ROOT', self.root), ('OWNER_UID', os.geteuid()),
                            ('BEFORE', source_pin),
                            ('LOCK_PIN', {'dev': lock_info.st_dev, 'ino': lock_info.st_ino})]:
            item = patch.object(install, name, value); item.start(); self.addCleanup(item.stop)

    def transaction(self, request='6963999999'):
        value = install.Transaction(request, 'a' * 40)
        self.addCleanup(value.close)
        return value

    def assert_other_state_untouched(self):
        self.assertEqual(self.training_hold.read_bytes(), b'KEEP_OWNER_HOLD\n')
        self.assertEqual(self.counter.read_bytes(), b'{"untouched":true}\n')
        self.assertEqual({'dev': self.lock.stat().st_dev, 'ino': self.lock.stat().st_ino}, install.LOCK_PIN)

    def make_replace_ack_loss(self, transaction):
        original = install.os.replace
        def effect_then_error(source, target, **kwargs):
            original(source, target, **kwargs)
            if source == transaction.stage_name:
                raise OSError('injected rename acknowledgement loss')
        return patch.object(install.os, 'replace', side_effect=effect_then_error)

    def test_real_install_changes_only_exact_source_and_private_evidence(self):
        tx = self.transaction(); result = tx.install()
        self.assertEqual(result['status'], 'SOURCE_FILE_INSTALLED')
        self.assertTrue(result['source_file_installed']); self.assertTrue(result['installation_accepted'])
        self.assertFalse(result['active_launcher_changed']); self.assertFalse(result['reconcile_required'])
        self.assertEqual(result['installed_identity'], install.metadata(self.target.stat()))
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), install.AFTER['sha256'])
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o775)
        self.assertEqual((self.target.stat().st_uid, self.target.stat().st_gid),
                         (install.BEFORE['uid'], install.BEFORE['gid']))
        attempt = self.root / 'state' / install.ATTEMPT
        self.assertEqual(stat.S_IMODE(attempt.stat().st_mode), 0o700)
        self.assertEqual((attempt / 'original.sh').read_bytes(), self.original)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in attempt.iterdir()))
        self.assertFalse((self.root / 'scripts' / tx.stage_name).exists())
        self.assertEqual(json.loads((attempt / '30_installed.json').read_text())['phase'], 'SOURCE_FILE_INSTALLED')
        self.assert_other_state_untouched()

    def test_preimage_or_existing_lease_rejection_has_no_attempt_or_replace(self):
        self.target.write_bytes(self.original + b'# drift\n')
        tx = self.transaction()
        with self.assertRaisesRegex(install.Hold, 'HOLD_HEADROOM_EXACT_NATIVE_PREIMAGE'):
            tx.install()
        self.assertFalse(tx.attempt_created); self.assertFalse(tx.replace_attempted); tx.close()
        self.target.write_bytes(self.original)
        # Restore fixture metadata pin only; production source pin is immutable.
        install.BEFORE = {**install.metadata(self.target.stat()), 'sha256': hashlib.sha256(self.original).hexdigest()}
        with self.lock.open('rb') as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy = self.transaction('6963999998')
            with self.assertRaises(BlockingIOError):
                busy.install()
            self.assertFalse(busy.attempt_created); self.assertFalse(busy.replace_attempted)
        self.assert_other_state_untouched()

    def test_fresh_cas_after_intent_preserves_foreign_target(self):
        tx = self.transaction(); original_record = tx.record
        def drift(name, fields):
            result = original_record(name, fields)
            if name == '20_replace_intent.json':
                replacement = self.root / 'scripts/foreign.tmp'
                replacement.write_bytes(self.original); replacement.chmod(0o775)
                os.replace(replacement, self.target)  # Same bytes, new inode.
            return result
        with patch.object(tx, 'record', side_effect=drift):
            with self.assertRaisesRegex(install.Hold, 'HOLD_HEADROOM_TARGET_CAS_DRIFT'):
                tx.install()
        self.assertFalse(tx.replace_attempted)
        self.assertNotEqual(self.target.stat().st_ino, install.BEFORE['ino'])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertTrue(tx.snapshot()['reconcile_required'])
        self.assert_other_state_untouched()

    def test_rename_ack_loss_requires_reconcile_and_explicit_owned_rollback(self):
        tx = self.transaction()
        with self.make_replace_ack_loss(tx):
            with self.assertRaises(OSError):
                tx.install()
        self.assertTrue(tx.replace_attempted); self.assertFalse(tx.replace_returned)
        self.assertIsNone(tx.snapshot()['source_file_installed'])
        self.assertEqual(tx.reconcile()['state'], 'OWNED_POSTIMAGE_PRESENT_UNACCEPTED')
        self.assertTrue(tx.snapshot()['reconcile_required']); self.assertFalse(tx.rollback_attempted)
        result = tx.rollback_owned()  # Explicit continuation, never entry policy.
        self.assertEqual(result['status'], 'SOURCE_RESTORED_UNACCEPTED')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o775)
        self.assertTrue(result['reconcile_required'])
        self.assert_other_state_untouched()

    def test_post_replace_fsync_failure_retains_attempt_and_blocks_new_request(self):
        tx = self.transaction(); original_replace = install.os.replace; original_fsync = install.os.fsync
        replaced = [False]; failed = [False]
        def mark(source, target, **kwargs):
            original_replace(source, target, **kwargs)
            if source == tx.stage_name: replaced[0] = True
        def fail_directory(fd):
            if replaced[0] and not failed[0] and fd == tx.scripts_fd:
                failed[0] = True
                raise OSError('injected directory fsync failure')
            return original_fsync(fd)
        with patch.object(install.os, 'replace', side_effect=mark), patch.object(install.os, 'fsync', side_effect=fail_directory):
            with self.assertRaises(OSError):
                tx.install()
        self.assertEqual(tx.reconcile()['state'], 'OWNED_POSTIMAGE_PRESENT_UNACCEPTED')
        self.assertFalse((self.root / 'state' / install.ATTEMPT / '30_installed.json').exists())
        tx.close()
        retry = self.transaction('6963999997')
        with self.assertRaisesRegex(install.Hold, 'HOLD_HEADROOM_PRIOR_ATTEMPT_RECONCILE'):
            retry.install()
        self.assertTrue(retry.snapshot()['reconcile_required'])
        self.assertIsNone(retry.snapshot()['source_file_installed'])
        self.assertFalse(retry.replace_attempted)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), install.AFTER['sha256'])
        self.assert_other_state_untouched()

    def test_rollback_refuses_same_bytes_owned_by_a_different_inode(self):
        tx = self.transaction()
        with self.make_replace_ack_loss(tx):
            with self.assertRaises(OSError): tx.install()
        replacement = self.root / 'scripts/foreign.tmp'
        replacement.write_bytes(self.target.read_bytes()); replacement.chmod(0o775)
        os.replace(replacement, self.target)
        foreign_inode = self.target.stat().st_ino
        with self.assertRaisesRegex(install.Hold, 'HOLD_HEADROOM_OWNED_POSTIMAGE_CAS'):
            tx.rollback_owned()
        self.assertFalse(tx.rollback_attempted)
        self.assertEqual(self.target.stat().st_ino, foreign_inode)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), install.AFTER['sha256'])
        self.assert_other_state_untouched()

    def test_entry_reports_unknown_effect_without_replay_and_import_surface_is_bounded(self):
        tx_class = install.Transaction
        original_replace = install.os.replace
        def effect_then_error(source, target, **kwargs):
            original_replace(source, target, **kwargs)
            raise OSError('injected outcome loss')
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '6963999996', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
             patch.object(install.os, 'replace', side_effect=effect_then_error):
            result = install.entry()
        self.assertIsNone(result['source_file_installed'])
        self.assertFalse(result['installation_accepted']); self.assertTrue(result['reconcile_required'])
        self.assertEqual(result['read_only_reconciliation']['state'], 'OWNED_POSTIMAGE_PRESENT_UNACCEPTED')
        self.assertFalse(result['automatic_retry']); self.assertFalse(result['automatic_rollback'])
        tree = ast.parse(Path(install.__file__).read_text())
        imports = {alias.name.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
                   if isinstance(node, ast.Import)}
        self.assertEqual(imports, {'fcntl', 'hashlib', 'json', 'os', 're', 'stat', 'time'})
        calls = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os'}
        self.assertFalse(calls & {'system', 'kill', 'killpg', 'execv', 'execve', 'fork', 'spawnv', 'posix_spawn'})
        self.assert_other_state_untouched()


if __name__ == '__main__':
    unittest.main(verbosity=2)
