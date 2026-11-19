import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

import owner_storage_reclaim as storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root, self.home = self.base / 'nox', self.base / 'home'
        self.root.mkdir(); self.home.mkdir()
        (self.root / 'state').mkdir()
        self.now = time.time() + 10 * 86400
        for name, value in (('ROOT', self.root), ('HOME_ROOT', self.home)):
            current = patch.object(storage, name, value)
            current.start(); self.addCleanup(current.stop)
        self.usage = {'used': set(), 'complete': True, 'active_package_manager': False,
                      'counts': {}, 'deleted_open_allocated_bytes': 0,
                      'deleted_open_unique_inodes': 0, 'scope': 'CURRENT_PID_NAMESPACE'}

    def file(self, path, prefix=b'cache bytes', size=2 * 1024 * 1024):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as stream:
            stream.write(prefix)
            block = b'x' * (1024 * 1024)
            remaining = size - len(prefix)
            while remaining:
                step = min(remaining, len(block))
                stream.write(block[:step]); remaining -= step
        return path

    def pip_file(self, prefix=b'cache bytes'):
        return self.file(self.home / '.cache/pip/http-v2/a/b/c/d/e' / ('a' * 56 + '.body'), prefix)

    def candidate(self, path):
        value, reason = storage.qualify(path, path.stat(), self.now, self.usage)
        self.assertIsNone(reason)
        self.assertIsNotNone(value)
        return value

    def test_only_regenerable_allowlist_and_protected_models_memory_source(self):
        approved = self.pip_file()
        self.assertEqual(self.candidate(approved)['category'], 'PIP_DOWNLOAD_CACHE')
        for path in (self.root / 'models/old.gguf', self.root / 'lora/checkpoint-5/optimizer.pt',
                     self.root / 'scripts/unused.py', self.root / 'memory/s03.db',
                     self.root / 'state/pc_shell/operator_ed25519', self.root / 'logs/chat.log',
                     self.root / 'logs/chat.log.1', self.root / 'logs/chat.log.2',
                     self.root / 'logs/owner_audit.log.8', self.root / 'logs/training.log.9',
                     self.root / 'media/models/model.safetensors.partial'):
            self.assertIsNone(storage.deletion_kind(path), path)
        self.assertEqual(storage.deletion_kind(self.root / 'logs/chat.log.3.gz')[0], 'OLD_DEBUG_LOG_ROTATION')

    def test_disguised_weight_header_and_partial_are_never_cache_candidates(self):
        for head in (b'GGUF' + b'0' * 20, struct.pack('<Q', 100) + b'{"tensor":', b'\x80\x04pickle'):
            path = self.pip_file(head)
            candidate, reason = storage.qualify(path, path.stat(), self.now, self.usage)
            self.assertIsNone(candidate)
            self.assertEqual(reason, 'MODEL_OR_SERIALIZED_STATE_HEADER')
        self.assertIsNone(storage.deletion_kind(self.home / '.cache/pip/http-v2' / ('b' * 56 + '.partial')))

    def test_recent_open_mapped_hardlinked_and_unknown_process_coverage_hold(self):
        path = self.pip_file()
        value, reason = storage.qualify(path, path.stat(), time.time(), self.usage)
        self.assertEqual(reason, 'RECENT_FILE')
        usage = dict(self.usage, used={(path.stat().st_dev, path.stat().st_ino)})
        self.assertEqual(storage.qualify(path, path.stat(), self.now, usage)[1], 'OPEN_OR_MEMORY_MAPPED')
        self.assertEqual(storage.qualify(path, path.stat(), self.now, dict(self.usage, complete=False))[1], 'PROCESS_INSPECTION_INCOMPLETE')
        self.assertEqual(storage.qualify(path, path.stat(), self.now, dict(self.usage, active_package_manager=True))[1], 'PACKAGE_MANAGER_ACTIVE')
        os.link(path, path.with_name('another-link'))
        self.assertEqual(storage.qualify(path, path.stat(), self.now, self.usage)[1], 'OWNERSHIP_LINK_TYPE_OR_SMALL_FILE')

    def test_core_requires_real_elf_et_core_header(self):
        path = self.file(self.root / 'core.1234', b'not a core')
        self.assertEqual(storage.qualify(path, path.stat(), self.now, self.usage)[1], 'NOT_ELF_CORE')
        head = bytearray(32); head[:4] = b'\x7fELF'; head[4] = 2; head[5] = 1; head[16:18] = b'\x04\x00'
        self.file(path, bytes(head))
        self.assertEqual(self.candidate(path)['category'], 'INACTIVE_ELF_CORE')

    def test_exact_unlink_rechecks_identity_and_does_not_follow_link(self):
        path = self.pip_file()
        candidate = self.candidate(path)
        # Test descriptor-relative unlink on a temporary tree; the production
        # ancestor-owner check is independently tested below (tmp is writable).
        opener = lambda value: os.open(Path(value).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        with patch.object(storage, 'open_parent', opener), patch.object(storage, 'process_usage', return_value=self.usage), patch.object(storage.time, 'time', return_value=self.now):
            row = storage.reclaim_candidate(candidate, time.monotonic() + 5)
        self.assertFalse(path.exists())
        self.assertEqual(row['state'], 'EXACT_AUDITED_FILE_UNLINKED')
        self.assertEqual(row['allocated_bytes_unlinked'], candidate['allocated_bytes'])
        changed = self.pip_file()
        candidate = self.candidate(changed)
        changed.write_bytes(b'changed')
        with patch.object(storage, 'open_parent', opener):
            with self.assertRaisesRegex(storage.StorageHold, 'IDENTITY_CHANGED'):
                storage.reclaim_candidate(candidate, time.monotonic() + 5)
        self.assertTrue(changed.exists())

    def test_reclaim_never_calls_unlink_when_fresh_scan_is_incomplete(self):
        path = self.pip_file()
        candidate = self.candidate(path)
        opener = lambda value: os.open(Path(value).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        with patch.object(storage, 'open_parent', opener), patch.object(storage, 'process_usage', return_value=dict(self.usage, complete=False)), patch.object(storage.time, 'time', return_value=self.now):
            with self.assertRaisesRegex(storage.StorageHold, 'PROCESS_INSPECTION_INCOMPLETE'):
                storage.reclaim_candidate(candidate, time.monotonic() + 5)
        self.assertTrue(path.exists())

    def test_root_walk_refuses_writable_parent_and_symlink(self):
        path = self.pip_file()
        self.home.chmod(0o777)
        with self.assertRaises(storage.StorageHold):
            storage.open_parent(path)
        self.home.chmod(0o700)
        link = self.base / 'alias'
        link.symlink_to(path.parent, target_is_directory=True)
        with self.assertRaises(storage.StorageHold):
            storage.plain(link / path.name)

    def test_process_fd_and_memory_maps_use_inode_not_private_filename(self):
        proc = self.base / 'proc'
        process = proc / '123'
        (process / 'fd').mkdir(parents=True)
        target = self.pip_file()
        (process / 'cmdline').write_bytes(b'python\0-m\0pip\0install\0hidden-credential\0')
        (process / 'fd/5').symlink_to(target)
        info = target.stat()
        (process / 'maps').write_text('0000-1000 r--p 0 %02x:%02x %d /private/model\n' % (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino))
        with patch.object(storage, 'PROC', proc):
            result = storage.process_usage(time.monotonic() + 2)
        self.assertTrue(result['complete'])
        self.assertTrue(result['active_package_manager'])
        self.assertIn((info.st_dev, info.st_ino), result['used'])
        public = {k: v for k, v in result.items() if k != 'used'}
        self.assertNotIn('hidden-credential', json.dumps(public))
        self.assertNotIn('/private/model', json.dumps(public))

    def test_teacher_hold_reasons_are_specific_and_never_delete(self):
        expected_path, expected_bytes = next(iter(storage.LEGACY_TEACHERS.items()))
        path = self.root / Path(expected_path).relative_to(Path('/root/nox'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'GGUF-small-test')
        usage = dict(self.usage, complete=False)
        row = storage.teacher_candidate_review(path, path.stat(), usage)
        self.assertEqual(row['observation'], 'OBSERVED_METADATA')
        self.assertEqual(row['observed_bytes'], len(b'GGUF-small-test'))
        self.assertEqual(row['hold_codes'], [
            'TEACHER_WEIGHTS_PROTECTED',
            'TWO_INDEPENDENT_SHA_VERIFIED_PC_AND_DRIVE_COPIES_REQUIRED',
            'EXPECTED_SIZE_MISMATCH',
            'PROCESS_INSPECTION_INCOMPLETE'])
        self.assertFalse(row['deletion_authorized'])
        self.assertTrue(path.exists())

        hardlink = self.base / 'second-link.gguf'
        os.link(path, hardlink)
        info = path.stat()
        busy = dict(self.usage, used={(info.st_dev, info.st_ino)})
        row = storage.teacher_candidate_review(path, info, busy)
        self.assertIn('EXPECTED_SIZE_MISMATCH', row['hold_codes'])
        self.assertIn('LINK_COUNT_NOT_ONE', row['hold_codes'])
        self.assertIn('OPEN_OR_MEMORY_MAPPED', row['hold_codes'])
        self.assertTrue(path.exists())

        row = storage.teacher_candidate_review(path, observation_error=PermissionError(
            13, 'API_KEY=secret-value path=/root/private traceback=private-stack'))
        self.assertIn('OSERROR_EACCES', row['hold_codes'])
        self.assertEqual(row['safe_exception_reason'], 'OSERROR_EACCES')
        serialized = json.dumps(row)
        for private in ('secret-value', '/root/private', 'private-stack'):
            self.assertNotIn(private, serialized)

        SecretNamedError = type('API_KEY_secret-value_/root/private_traceback', (Exception,), {})
        for bad_error in (
            SecretNamedError('API_KEY=secret-value /root/private traceback=private-stack'),
            storage.StorageHold('API_KEY_SECRET_VALUE'),
        ):
            row = storage.teacher_candidate_review(path, observation_error=bad_error)
            self.assertEqual(row['safe_exception_reason'],
                             'OBSERVATION_ERROR_UNCLASSIFIED' if isinstance(bad_error, SecretNamedError)
                             else 'STORAGE_HOLD_UNCLASSIFIED')
            serialized = json.dumps(row)
            for private in ('secret-value', 'API_KEY_SECRET_VALUE', '/root/private', 'private-stack'):
                self.assertNotIn(private, serialized)
        row = storage.teacher_candidate_review(path, observation_error=storage.StorageHold('HOLD_STORAGE_SYMLINK'))
        self.assertEqual(row['safe_exception_reason'], 'HOLD_STORAGE_SYMLINK')
        self.assertIn('HOLD_STORAGE_SYMLINK', row['hold_codes'])
        row = storage.teacher_candidate_review(path, observation_error='SYMLINK_NOT_FOLLOWED')
        self.assertIn('SYMLINK_NOT_FOLLOWED', row['hold_codes'])
        row = storage.teacher_candidate_review(path)
        self.assertIn('NOT_OBSERVED_WITHIN_BOUNDED_AUDIT', row['hold_codes'])
        with patch.object(storage.os, 'geteuid', return_value=path.stat().st_uid + 1):
            row = storage.teacher_candidate_review(path, path.stat(), self.usage)
        self.assertIn('OWNER_UID_MISMATCH', row['hold_codes'])
        with patch.object(storage.stat, 'S_ISREG', return_value=False):
            row = storage.teacher_candidate_review(path, path.stat(), self.usage)
        self.assertIn('FILE_NOT_REGULAR', row['hold_codes'])
        self.assertFalse(row['deletion_authorized'])
        self.assertTrue(path.exists())
        self.assertIsNone(storage.teacher_candidate_review('/tmp/not-a-teacher.gguf'))

    def test_teacher_holds_are_in_audit_receipt_with_no_file_action(self):
        expected_path = next(iter(storage.LEGACY_TEACHERS))
        path = self.root / Path(expected_path).relative_to(Path('/root/nox'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'GGUF-temp')
        budget = {'ssd': {'total_bytes': 200 * GIB, 'used_bytes': 180 * GIB, 'free_bytes': 20 * GIB},
                  'tmpfs': {'total_bytes': 50 * GIB, 'used_bytes': 30 * GIB, 'free_bytes': 20 * GIB},
                  'cgroup': {'headroom_bytes': 120 * GIB}}
        with patch.object(storage, 'root_specs', return_value=[('NOX', self.root)]), \
             patch.object(storage, 'process_usage', return_value=dict(self.usage, complete=False)), \
             patch.object(storage, 'filesystem_budget', return_value=budget):
            result = storage.audit('123', 'a' * 40)
        row = next(item for item in result['teacher_candidate_holds']
                   if item['path_id'] == storage.teacher_candidate_review(path)['path_id'])
        self.assertEqual(row['observation'], 'OBSERVED_METADATA')
        self.assertIn('PROCESS_INSPECTION_INCOMPLETE', row['hold_codes'])
        self.assertIn('TEACHER_WEIGHTS_PROTECTED', row['hold_codes'])
        self.assertFalse(row['deletion_authorized'])
        self.assertTrue(path.exists())
        self.assertEqual(result['files_deleted'], 0)
        folder = self.root / 'models'
        first = self.file(folder / 'model.gguf', b'GGUF', 8 * 1024 * 1024)
        other = folder / 'other'; other.mkdir()
        os.link(first, other / 'linked.gguf')
        self.file(other / 'model.gguf', b'GGUF', 8 * 1024 * 1024)
        budget = {'ssd': {'total_bytes': 200 * GIB, 'used_bytes': 180 * GIB, 'free_bytes': 20 * GIB},
                  'tmpfs': {'total_bytes': 50 * GIB, 'used_bytes': 30 * GIB, 'free_bytes': 20 * GIB},
                  'cgroup': {'headroom_bytes': 120 * GIB}}
        with patch.object(storage, 'root_specs', return_value=[('NOX', self.root)]), patch.object(storage, 'process_usage', return_value=self.usage), patch.object(storage, 'filesystem_budget', return_value=budget):
            result = storage.audit('123', 'a' * 40)
        group = result['categories']['OTHER_MODEL_WEIGHTS_PROTECTED']
        self.assertEqual(group['files'], 3)
        self.assertEqual(group['unique_inodes'], 2)
        self.assertEqual(group['repeated_inode_paths'], 1)
        self.assertEqual(result['distinct_inode_same_name_size_groups'], 1)
        self.assertFalse(result['content_duplicate_verified'])
        self.assertFalse(result['weight_eviction']['allowed'])
        self.assertEqual(result['cleanup_candidates'], [])

    def test_public_summary_excludes_paths_and_private_candidate_data(self):
        value = {'schema': storage.SCHEMA, 'cleanup_candidates': [{'path': '/private/name',
                 'category': 'PIP_DOWNLOAD_CACHE', 'allocated_bytes': 10,
                 'prefix_sha256': 'a' * 64}], 'source_sha': 'hidden',
                 'skipped': [{'path_id': 'private-path-id', 'reason': 'HOLD_STORAGE_IDENTITY_CHANGED'}]}
        raw = json.dumps(storage.public_summary(value))
        self.assertNotIn('/private/name', raw)
        self.assertNotIn('private-path-id', raw)
        self.assertNotIn('hidden', raw)
        self.assertIn('PIP_DOWNLOAD_CACHE', raw)

    def test_receipt_pin_freshness_and_permissions(self):
        receipt = {'schema': storage.SCHEMA, 'instance_id': storage.INSTANCE, 'action': 'AUDIT',
                   'request': '12', 'finished_at': time.time() - 2000, 'cleanup_candidates': [],
                   'helper_sha256': hashlib.sha256(Path(storage.__file__).read_bytes()).hexdigest()}
        path = storage.receipt_directory() / 'audit_12.json'
        sha = storage.write_receipt(path, receipt)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(storage.StorageHold, 'SHA_CHANGED'):
            storage.reclaim('13', 'a' * 40, '12', 'f' * 64)
        with self.assertRaisesRegex(storage.StorageHold, 'FRESHNESS'):
            storage.reclaim('13', 'a' * 40, '12', sha)

    def test_ram_decision_never_calls_full_base_or_ram_a_durable_backup(self):
        budget = {'ssd': {'free_bytes': 15_729_852_416}, 'tmpfs': {'free_bytes': 20_749_209_600},
                  'cgroup': {'headroom_bytes': 140_000_000_000}}
        value = storage.placement(budget, {'TRAINING_HF_BASE_PROTECTED': {'unique_logical_bytes': 73_000_000_000}})
        self.assertFalse(value['hf_base_full_tmpfs_fit_now'])
        self.assertFalse(value['ram_is_durable_backup'])
        self.assertFalse(value['extra_full_weight_copy_created'])
        self.assertEqual(value['selected_media_new_package_placement'], 'RAM_CANDIDATE_REQUIRES_INSTALLER_SHA_AND_RECHECK')


GIB = 1024 ** 3
if __name__ == '__main__':
    unittest.main()
