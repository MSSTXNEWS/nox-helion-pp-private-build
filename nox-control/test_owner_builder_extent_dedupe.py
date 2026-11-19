"""Bounded fixture files only; the real kernel deduplication ioctl is never used."""
from contextlib import ExitStack
from pathlib import Path
import errno
import hashlib
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import owner_builder_extent_dedupe as entry

REAL_FILESYSTEM = entry.filesystem


class ExtentDedupeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b'abcd' * 2048 + b'unchanged-tail'
        self.paths = (self.root / 'archive.safetensors', self.root / 'kept.safetensors')
        for path in self.paths:
            path.write_bytes(self.data)
            path.chmod(0o666)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(entry, 'SIZE', len(self.data)))
        self.stack.enter_context(patch.object(entry, 'SHA', hashlib.sha256(self.data).hexdigest()))
        self.stack.enter_context(patch.object(entry, 'CHUNK', 4096))
        self.stack.enter_context(patch.object(entry, 'HASH_RATE', 10**12))
        self.stack.enter_context(patch.object(entry, 'FILES', tuple(zip(('ARCHIVE', 'KEPT'), self.paths))))
        self.stack.enter_context(patch.object(entry, 'stopped', return_value=False))
        self.fs = self.stack.enter_context(patch.object(entry, 'filesystem', return_value={
            'magic': 0x58465342, 'block_size': 4096, 'fsid': (1, 2), 'read_only': False}))

    def result(self):
        return {'state': 'PREFLIGHT', 'ranges_attempted': 0, 'ranges_completed': 0,
                'kernel_reported_range_bytes': 0, 'destination_write_opened': False,
                'full_sha_before_verified': False, 'full_sha_after_verified': False}

    def test_kernel_abi_exactly_one_destination_and_zero_reserved_fields(self):
        def ioctl(fd, request, buffer, mutable):
            self.assertEqual(fd, 100)
            self.assertEqual(request, 0xC0189436)
            self.assertIs(mutable, True)
            self.assertEqual(len(buffer), 56)
            value = list(entry.REQUEST.unpack(buffer))
            self.assertEqual(value, [4096, 4096, 1, 0, 0, 101, 4096, 0, 0, 0])
            value[7] = 4096
            buffer[:] = entry.REQUEST.pack(*value)
            return 0
        with patch.object(entry.fcntl, 'ioctl', side_effect=ioctl):
            self.assertEqual(entry.range_ioctl(100, 101, 4096), (4096, 0))

    def test_read_only_local_fstatfs_abi_matches_statvfs_block_size(self):
        fd = entry.open_regular(self.paths[0])
        try:
            value = REAL_FILESYSTEM(fd)
            self.assertEqual(value['block_size'], os.fstatvfs(fd).f_bsize)
            self.assertEqual(len(value['fsid']), 2)
            self.assertIs(type(value['magic']), int)
        finally:
            os.close(fd)

    def test_overlay_rejected_before_write_open_or_hash(self):
        self.fs.return_value = {**self.fs.return_value, 'magic': 0x794C7630}
        real_open = os.open
        with patch.object(entry.os, 'open', wraps=real_open) as opened, \
             patch.object(entry, 'hash_pair') as hashing, \
             patch.object(entry, 'range_ioctl') as ioctl:
            result = self.result()
            entry.operate(result)
        self.assertEqual(result['state'], 'UNSUPPORTED_FILESYSTEM_NO_WRITE_OPEN')
        self.assertFalse(result['destination_write_opened'])
        self.assertTrue(all(not call.args[1] & os.O_RDWR for call in opened.call_args_list))
        hashing.assert_not_called()
        ioctl.assert_not_called()

    def test_exact_content_mismatch_cannot_reach_ioctl(self):
        self.paths[1].write_bytes(b'X' + self.data[1:])
        with patch.object(entry, 'range_ioctl') as ioctl:
            with self.assertRaisesRegex(entry.Hold, 'FULL_SHA_MISMATCH'):
                entry.operate(self.result())
        ioctl.assert_not_called()
        self.assertEqual(self.paths[1].read_bytes(), b'X' + self.data[1:])

    def test_same_inode_and_symlink_are_never_dedup_targets(self):
        with patch.object(entry, 'FILES', (('ONE', self.paths[0]), ('SAME', self.paths[0]))), \
             patch.object(entry, 'range_ioctl') as ioctl:
            with self.assertRaisesRegex(entry.Hold, 'SEPARATE_INODES_SAME_FS'):
                entry.operate(self.result())
            ioctl.assert_not_called()
        alias = self.root / 'alias'
        alias.symlink_to(self.paths[1])
        with patch.object(entry, 'FILES', (('ONE', self.paths[0]), ('SYMLINK', alias))), \
             patch.object(entry, 'range_ioctl') as ioctl:
            with self.assertRaises(OSError):
                entry.operate(self.result())
            ioctl.assert_not_called()

    def test_full_ranges_keep_separate_inodes_modes_tail_and_do_not_invent_savings(self):
        before = [path.stat() for path in self.paths]
        with patch.object(entry, 'range_ioctl', return_value=(4096, 0)) as ioctl, \
             patch.object(entry, 'free_bytes', return_value=123456):
            result = self.result()
            entry.operate(result)
        self.assertEqual(result['state'], 'SELECTED_RANGES_SHARED_CONTENT_VERIFIED')
        self.assertEqual([call.args[2] for call in ioctl.call_args_list], [0, 4096])
        self.assertEqual(result['kernel_reported_range_bytes'], 8192)
        self.assertEqual(result['global_free_space_delta_bytes'], 0)
        self.assertTrue(result['full_sha_before_verified'])
        self.assertTrue(result['full_sha_after_verified'])
        self.assertTrue(result['separate_inodes_paths_and_permissions_preserved'])
        for path, old in zip(self.paths, before):
            self.assertEqual(entry.identity(path.stat()), entry.identity(old))
            self.assertEqual(path.read_bytes(), self.data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o666)

    def test_ioctl_unsupported_has_no_fallback_and_preserves_post_hash(self):
        for code in (errno.EOPNOTSUPP, errno.ENOTTY):
            with self.subTest(errno=code), \
                 patch.object(entry, 'range_ioctl', side_effect=OSError(code, 'fixture')) as ioctl:
                result = self.result()
                entry.operate(result)
                self.assertEqual(result['state'], 'UNSUPPORTED_CONTENT_VERIFIED')
                self.assertEqual(result['kernel_reported_range_bytes'], 0)
                self.assertTrue(result['full_sha_after_verified'])
                ioctl.assert_called_once()

    def test_destination_negative_status_can_report_partial_not_full_sweep(self):
        with patch.object(entry, 'range_ioctl', side_effect=[(4096, 0), (0, -errno.EOPNOTSUPP)]):
            result = self.result()
            entry.operate(result)
        self.assertEqual(result['state'], 'PARTIAL_UNSUPPORTED_CONTENT_VERIFIED')
        self.assertEqual(result['ranges_completed'], 1)
        self.assertEqual(result['kernel_reported_range_bytes'], 4096)
        self.assertTrue(result['full_sha_after_verified'])

    def test_concurrent_write_is_detected_without_restoring_or_overwriting_it(self):
        def concurrent_write(_source, destination, _offset):
            os.pwrite(destination, b'Z', 0)  # Model an unrelated writer, not this ioctl.
            return 0, 1
        with patch.object(entry, 'range_ioctl', side_effect=concurrent_write):
            result = self.result()
            with self.assertRaisesRegex(entry.Hold, 'FULL_SHA_MISMATCH'):
                entry.operate(result)
        self.assertFalse(result['full_sha_after_verified'])
        self.assertEqual(self.paths[1].read_bytes(), b'Z' + self.data[1:])
        self.assertEqual(self.paths[0].read_bytes(), self.data)

    def test_short_kernel_result_is_never_called_complete(self):
        with patch.object(entry, 'range_ioctl', return_value=(1024, 0)) as ioctl:
            result = self.result()
            entry.operate(result)
        self.assertEqual(result['range_outcome'], 'PARTIAL_KERNEL_RANGE')
        self.assertEqual(result['ranges_completed'], 0)
        self.assertEqual(result['kernel_reported_range_bytes'], 1024)
        ioctl.assert_called_once()

    def test_receipt_is_private_and_never_replaces_an_existing_record(self):
        path = self.root / 'receipt.json'
        pin = entry.write_receipt(path, {'schema': entry.SCHEMA, 'private_content_exported': False})
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pin)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        old = path.read_bytes()
        with self.assertRaises(FileExistsError):
            entry.write_receipt(path, {'changed': True})
        self.assertEqual(path.read_bytes(), old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
