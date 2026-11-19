"""Only temporary synthetic duplicates; no native paths, services or weights."""
from contextlib import ExitStack
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import owner_builder_archive_reclaim as entry


class ArchiveReclaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive/adapter_model.safetensors'
        self.canonical = self.root / 'canonical/adapter_model.safetensors'
        self.ram = self.root / 'ram/builder.safetensors'
        self.data = b'SYNTHETIC BUILDER\n' * 129
        self.config = b'{"fixture":true}\n'
        for p in (self.archive, self.canonical, self.ram):
            p.parent.mkdir(); p.write_bytes(self.data); p.chmod(0o666)
        for p in (self.archive.parent, self.canonical.parent):
            (p / 'adapter_config.json').write_bytes(self.config)
            (p / 'receipt.sidecar').write_bytes(b'PRESERVE THIS SIDECAR')
        (self.root / 'backup').mkdir()
        state = self.root / 'state'; state.mkdir()
        (state / 'owner_maintenance.lock').touch()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for key, value in {'ROOT': self.root, 'STATE': self.root / 'state',
                'ARCHIVE': self.archive, 'CANONICAL': self.canonical, 'RAM': self.ram,
                'SIZE': len(self.data), 'SHA': hashlib.sha256(self.data).hexdigest(),
                'CONFIG_SHA': hashlib.sha256(self.config).hexdigest(), 'RATE': 10**12}.items():
            self.stack.enter_context(patch.object(entry, key, value))
        self.stack.enter_context(patch.object(entry, 'stop', return_value=False))
        self.visibility = {'visibility': 'COMPLETE', 'complete': True, 'known_reference_count': 0,
                           'partial_visibility_is_not_proof_of_inactivity': True}
        self.usage = self.stack.enter_context(patch.object(entry, 'usage', return_value=self.visibility))
        self.result = {'request': '123', 'source_sha': 'a' * 40, 'fresh_archive_deleted': False}
        self.proof = {'schema': 'SYNTHETIC_EXTERNAL_OWNER_PROOF',
                      'evidence_origin': 'SYNTHETIC_FIXTURE', 'no_raw_ids': True}
        self.originals = {p: (entry.identity(p.stat()), p.read_bytes()) for p in (self.canonical, self.ram,
            self.archive.parent / 'adapter_config.json', self.canonical.parent / 'adapter_config.json',
            self.archive.parent / 'receipt.sidecar', self.canonical.parent / 'receipt.sidecar')}

    def operate(self):
        entry.operate(self.result, None, self.proof, time.monotonic() + 10)
        return self.result

    def assert_preserved(self):
        for p, (old, content) in self.originals.items():
            self.assertEqual(entry.identity(p.stat()), old)
            self.assertEqual(p.read_bytes(), content)

    def test_exact_unlink_partial_visibility_private_map_and_no_invented_free(self):
        old = entry.identity(self.archive.stat())
        real_rename = entry.rename_noreplace
        def rename_after_durable_map(*args):
            q = self.root / 'backup/builder-archive-reclaim-123'
            row = json.loads((q / 'restore-map.json').read_bytes())
            self.assertEqual(row['original_metadata'], old)
            self.assertEqual(row['external_owner_drive_readback'], self.proof)
            self.assertFalse(row['native_direct_drive_readback'])
            self.assertEqual(q.stat().st_mode & 0o777, 0o700)
            self.assertEqual((q / 'restore-map.json').stat().st_mode & 0o777, 0o600)
            real_rename(*args)
        with patch.object(entry, 'rename_noreplace', side_effect=rename_after_durable_map), \
             patch.object(entry, 'free_bytes', return_value=50000):
            result = self.operate()
        self.assertEqual(result['state'], 'EXACT_ARCHIVE_REMOVED_CANONICAL_RAM_AND_DRIVE_RETAINED')
        self.assertFalse(self.archive.exists())
        self.assertTrue(result['fresh_archive_deleted'])
        self.assertEqual(result['global_free_space_delta_bytes'], 0)
        self.assertEqual(result['usage_before']['visibility'], 'COMPLETE')
        self.assertFalse(result['global_free_delta_attributed_exclusively_to_operation'])
        self.assert_preserved()

    def test_foreign_reference_blocks_without_namespace_change(self):
        self.usage.return_value = {**self.visibility, 'known_reference_count': 1}
        with patch.object(entry, 'rename_noreplace') as rename:
            result = self.operate()
        rename.assert_not_called()
        self.assertIn('KNOWN_PROCESS_REFERENCE', result['reason'])
        self.assertEqual(self.archive.read_bytes(), self.data)
        self.assert_preserved()

    def test_stop_blocks_archive_cleanup_before_any_rename(self):
        (self.root / 'STOP').write_text('fixture hold')
        with patch.object(entry, 'dependencies', return_value=(None, self.proof)), \
             patch.object(entry, 'stop', return_value=True), \
             patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
             patch.object(entry, 'rename_noreplace') as rename:
            with self.assertRaisesRegex(entry.Hold, 'OWNER_STOP'):
                entry.main()
        rename.assert_not_called()
        self.assertTrue(self.archive.exists())
        self.assert_preserved()

    def test_missing_external_backup_proof_holds_before_archive_cleanup(self):
        here = Path(__file__).parent
        bundle = {entry.PROC_NAME: base64.b64encode((here / entry.PROC_NAME).read_bytes()).decode()}
        with patch.object(entry, 'BUNDLE', bundle), \
             patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
             patch.object(entry, 'rename_noreplace') as rename:
            with self.assertRaisesRegex(entry.Hold, 'EXTERNAL_PROOF_BOUND'):
                entry.main()
        rename.assert_not_called()
        self.assertTrue(self.archive.exists())
        self.assert_preserved()

    def test_incomplete_dependency_scan_holds_before_archive_quarantine(self):
        self.usage.return_value = {**self.visibility, 'visibility': 'PARTIAL', 'complete': False}
        with patch.object(entry, 'rename_noreplace') as rename:
            result = self.operate()
        rename.assert_not_called()
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertIn('PROCESS_INSPECTION_INCOMPLETE', result['reason'])
        self.assertTrue(self.archive.exists())
        self.assert_preserved()

    def test_corrupt_restore_map_readback_holds_before_any_rename(self):
        real_regular = entry.regular
        def corrupt_before_reopen(parent, name, **kwargs):
            if name == 'restore-map.json':
                fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.pwrite(fd, b'!', 0); os.fsync(fd)
                finally:
                    os.close(fd)
            return real_regular(parent, name, **kwargs)
        with patch.object(entry, 'regular', side_effect=corrupt_before_reopen), \
             patch.object(entry, 'rename_noreplace') as rename:
            result = self.operate()
        rename.assert_not_called()
        self.assertEqual(result['state'], 'HOLD_ARCHIVE_NOT_REMOVED')
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertIn('CHANGED', result['reason'])
        self.assertEqual(self.archive.read_bytes(), self.data)
        self.assert_preserved()

    def test_each_full_copy_hash_required_before_deletion(self):
        for path in (self.archive, self.canonical, self.ram):
            with self.subTest(path=path.name):
                path.write_bytes(b'X' + self.data[1:])
                with patch.object(entry, 'rename_noreplace') as rename:
                    result = self.operate()
                rename.assert_not_called()
                self.assertFalse(result['fresh_archive_deleted'])
                self.assertIn('HASH_OR_METADATA_CHANGED', result['reason'])
                path.write_bytes(self.data)

    def test_rename_success_fsync_failure_rolls_back_without_unlink(self):
        real_sync = entry.fsync_dir
        failed = False
        def sync(fd):
            nonlocal failed
            q = self.root / 'backup/builder-archive-reclaim-123/archive-adapter_model.safetensors'
            if q.exists() and not failed:
                failed = True
                raise OSError(errno.EIO, 'fixture')
            real_sync(fd)
        with patch.object(entry, 'fsync_dir', side_effect=sync):
            result = self.operate()
        self.assertTrue(failed)
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertTrue(result['archive_name_restored_without_overwrite'])
        self.assertEqual(self.archive.read_bytes(), self.data)
        self.assert_preserved()

    def test_preexisting_writer_change_detected_after_quarantine_and_restored(self):
        real_rename = entry.rename_noreplace
        changed = False
        def writer_after_rename(*args):
            nonlocal changed
            real_rename(*args)
            if not changed:
                changed = True
                q = self.root / 'backup/builder-archive-reclaim-123/archive-adapter_model.safetensors'
                with q.open('r+b') as stream:
                    stream.write(b'X')
        with patch.object(entry, 'rename_noreplace', side_effect=writer_after_rename):
            result = self.operate()
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertTrue(result['archive_name_restored_without_overwrite'])
        self.assertEqual(self.archive.read_bytes(), b'X' + self.data[1:])
        self.assert_preserved()

    def test_reappeared_foreign_original_is_never_overwritten(self):
        real_rename = entry.rename_noreplace
        def foreign_after_rename(*args):
            real_rename(*args)
            self.archive.write_bytes(b'FOREIGN NEW ORIGINAL')
        with patch.object(entry, 'rename_noreplace', side_effect=foreign_after_rename):
            result = self.operate()
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertTrue(result['quarantined_file_retained_for_owner'])
        self.assertEqual(self.archive.read_bytes(), b'FOREIGN NEW ORIGINAL')
        self.assertEqual((self.root / 'backup/builder-archive-reclaim-123/archive-adapter_model.safetensors').read_bytes(), self.data)
        self.assert_preserved()

    def test_path_replaced_between_last_check_and_rename_is_held_and_returned(self):
        real_rename = entry.rename_noreplace
        changed = False
        def replace_then_rename(*args):
            nonlocal changed
            if not changed:
                changed = True
                replacement = self.archive.parent / 'replacement'
                replacement.write_bytes(b'X' * len(self.data)); replacement.chmod(0o666)
                os.replace(replacement, self.archive)
            real_rename(*args)
        with patch.object(entry, 'rename_noreplace', side_effect=replace_then_rename):
            result = self.operate()
        self.assertIn('RENAMED_INODE_CHANGED', result['reason'])
        self.assertFalse(result['fresh_archive_deleted'])
        self.assertTrue(result['archive_name_restored_without_overwrite'])
        self.assertEqual(self.archive.read_bytes(), b'X' * len(self.data))
        self.assert_preserved()

    def test_already_absent_is_not_a_fresh_delete(self):
        self.archive.unlink()
        with patch.object(entry, 'rename_noreplace') as rename:
            result = self.operate()
        rename.assert_not_called()
        self.assertEqual(result['state'], 'ARCHIVE_ALREADY_ABSENT_CANONICAL_AND_RAM_RETAINED')
        self.assertFalse(result['fresh_archive_deleted'])
        self.assert_preserved()

    def test_free_space_readback_occurs_after_own_deleted_inode_fd_closed(self):
        original_inode = self.archive.stat().st_ino
        calls = 0
        def space(_fd):
            nonlocal calls
            calls += 1
            if calls > 1:
                for p in Path('/proc/self/fd').iterdir():
                    try:
                        info = p.stat()
                    except FileNotFoundError:
                        continue
                    self.assertNotEqual(info.st_ino, original_inode)
            return 1234
        with patch.object(entry, 'free_bytes', side_effect=space):
            result = self.operate()
        self.assertEqual(calls, 2)
        self.assertTrue(result['fresh_archive_deleted'])

    def test_post_unlink_fsync_failure_reports_actual_delete_and_keeps_restore_map(self):
        real_sync = entry.fsync_dir
        def sync(fd):
            q = self.root / 'backup/builder-archive-reclaim-123'
            if (q / 'unlink-intent.json').exists() and not (q / 'archive-adapter_model.safetensors').exists():
                raise OSError(errno.EIO, 'fixture')
            return real_sync(fd)
        with patch.object(entry, 'fsync_dir', side_effect=sync):
            result = self.operate()
        self.assertEqual(result['state'], 'ARCHIVE_REMOVED_POSTCHECK_HELD')
        self.assertTrue(result['fresh_archive_deleted'])
        self.assertTrue((self.root / 'backup/builder-archive-reclaim-123/restore-map.json').exists())
        self.assert_preserved()


class ScopeTests(unittest.TestCase):
    def test_exact_pinned_external_readback_and_proc_bundle(self):
        here = Path(__file__).parent
        bundle = {name: base64.b64encode((here / name).read_bytes()).decode()
                  for name in (entry.PROC_NAME, entry.PROOF_NAME)}
        with patch.object(entry, 'BUNDLE', bundle):
            proc, proof = entry.dependencies()
        self.assertTrue(callable(proc.probe_process))
        self.assertEqual(entry.digest(entry.encoded(proof)), entry.PROOF_SHA)
        proof['parts'][0]['bytes'] -= 1
        bundle[entry.PROOF_NAME] = base64.b64encode(entry.encoded(proof)).decode()
        with patch.object(entry, 'BUNDLE', bundle), self.assertRaisesRegex(entry.Hold, 'EXTERNAL_PROOF_PIN'):
            entry.dependencies()

    def test_usage_only_ignores_own_exact_readonly_fd(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); own = os.getpid(); foreign = own + 1
            for pid in (own, foreign): (root / str(pid)).mkdir()
            def probe(pid, *_):
                return {'candidate_fd_maps_complete': True, 'identity_stable': True, 'errors': [],
                        'references': [{'kind': 'FD', 'fd': 8, 'access': 'READ_ONLY', 'builders': ['BUILDER_ARCHIVE']},
                                       {'kind': 'FD', 'fd': 9, 'access': 'READ_WRITE', 'builders': ['BUILDER_ARCHIVE']}]}
            proc = types.SimpleNamespace(PROC=root, NAMESPACES=(), MAX_PIDS=8, probe_process=probe, ProbeBudget=TimeoutError)
            result = entry.usage(proc, {}, {8, 9}, time.monotonic() + 2)
        self.assertEqual(result['own_exact_readonly_fds_ignored'], 1)
        self.assertEqual(result['known_reference_count'], 3)


if __name__ == '__main__':
    unittest.main()
