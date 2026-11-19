#!/usr/bin/env python3
"""V11 read-only mount discovery regressions; no live guest or write calls."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

MODULE = Path(__file__).with_name('owner_native_inspect.py')
spec = importlib.util.spec_from_file_location('nox_owner_mount_probe', MODULE)
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)

def fixture(free_bytes=300_000_000_000):
    return SimpleNamespace(f_blocks=100_000_000, f_bavail=free_bytes // 4096,
                           f_frsize=4096)

class MountProbeTests(unittest.TestCase):
    def test_external_seekable_candidate_is_metadata_only(self):
        data = ('1 0 0:1 / / rw - overlay overlay rw\n'
                '2 1 8:2 / /data rw - ext4 /dev/sdb rw\n')
        x = inspect.storage_mount_metadata(data, lambda p: fixture())
        self.assertEqual([r['path'] for r in x['mounts']], ['/', '/data'])
        self.assertEqual(x['mounts'][1]['free_bytes'], (300_000_000_000 // 4096) * 4096)
        self.assertEqual(x['seekability'], 'NOT_TESTED')
        self.assertEqual(x['write_access'], 'NOT_TESTED')

    def test_excludes_proc_and_unrelated_secret_paths(self):
        data = ('1 0 0:1 / /proc rw - proc proc rw\n'
                '2 1 8:2 / /run/secrets rw - ext4 /dev/sdb rw\n'
                '3 1 8:3 / /workspace/weights rw - ext4 /dev/sdc rw\n')
        x = inspect.storage_mount_metadata(data, lambda p: fixture())
        self.assertEqual([r['path'] for r in x['mounts']], ['/workspace/weights'])

    def test_stat_error_does_not_claim_capacity(self):
        def fail(path):
            raise PermissionError('not authorized')
        x = inspect.storage_mount_metadata('1 0 8:2 / /data rw - nfs remote rw', fail)
        self.assertEqual(x['mounts'][0]['status'], 'UNKNOWN_STATVFS')
        self.assertNotIn('free_bytes', x['mounts'][0])

    def test_incomplete_probe_is_not_full_storage_attestation(self):
        x = inspect.storage_mount_metadata('malformed\n1 0 0:1 / /data rw - tmpfs tmp rw',
                                            lambda p: fixture())
        self.assertEqual(x['mounts'], [])
        self.assertEqual(x['scope'], 'ALLOWLISTED_ONLY_NOT_EXHAUSTIVE')

if __name__ == '__main__':
    unittest.main()
