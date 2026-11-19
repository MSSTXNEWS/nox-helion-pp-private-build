"""Owner attribution tests with synthetic procfs and cgroup-v2 fixtures."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import owner_native_inspect as inspect


class MappedMemoryAttributionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.proc = Path(folder.name) / 'proc'
        self.group = Path(folder.name) / 'cgroup'
        self.group.mkdir()
        (self.group / 'cgroup.controllers').write_text('memory\n')
        (self.group / 'cgroup.type').write_text('domain\n')
        (self.group / 'cgroup.procs').write_text('101\n202\n')
        self.roles = {101: ('nox-dispatcher-t855u', 1001), 202: ('nox-ds41-8098', None)}
        self.secret = b'/private/path with space/DO_NOT_EXPORT'
        self.file_map = b'1000-2000 rw-p 00000000 00:0a 999 ' + self.secret
        self.anon_map = b'2000-3000 rw-p 00000000 00:00 0 '
        self.shmem_map = b'3000-4000 rw-s 00000000 00:01 998 /memfd:PRIVATE_MEMFD (deleted)'
        self.maps = b'\n'.join((self.file_map, self.anon_map, self.shmem_map)) + b'\n'
        self.rollup = b'Pss: 120010 kB\nPss_Anon: 10 kB\nPss_File: 100000 kB\nPss_Shmem: 20000 kB\n'
        self.smaps = (
            self.file_map + b'\nRss: 199990 kB\nPss: 100005 kB\nAnonymous: 5 kB\n'
            + self.anon_map + b'\nRss: 5 kB\nPss: 5 kB\nAnonymous: 5 kB\n'
            + self.shmem_map + b'\nRss: 40000 kB\nPss: 20000 kB\nAnonymous: 0 kB\n')
        self.add_proc(101, 1001)
        self.add_proc(202, 2002)

    def add_proc(self, pid, ticks):
        root = self.proc / str(pid)
        root.mkdir(parents=True, exist_ok=True)
        fields = ['S', '1', '1'] + ['0'] * 16 + [str(ticks)]
        (root / 'stat').write_text(f'{pid} (synthetic) ' + ' '.join(fields) + '\n')
        (root / 'cgroup').write_text('0::/\n')
        (root / 'maps').write_bytes(self.maps)
        (root / 'smaps_rollup').write_bytes(self.rollup)
        (root / 'smaps').write_bytes(self.smaps)
        return root

    def run_capture(self, read_roles=None):
        return inspect.mapped_memory_attribution(proc_root=self.proc, cgroup_root=self.group,
            read_roles=read_roles or (lambda: (101, dict(self.roles))))

    def assert_hold(self, receipt, state):
        self.assertEqual(receipt, {'schema': 'NOX_MAPPED_MEMORY_ATTRIBUTION_V1',
                                  'read_only': True, 'state': state})

    def test_root_scope_proportional_sums_redact_paths_and_raw_inodes(self):
        with patch.object(inspect.os, 'getpid', return_value=1234):
            receipt = self.run_capture()
        self.assertEqual(receipt['state'], 'OBSERVED')
        self.assertEqual(receipt['verified_members'], 2)
        self.assertEqual(receipt['by_role']['nox-ds41-8098'], {
            'processes': 1, 'pss_file_kib': 100000, 'pss_anon_kib': 10, 'pss_shmem_kib': 20000})
        file_row, shmem_row = receipt['inode_candidates']
        self.assertEqual(file_row['inode_sha256'], hashlib.sha256(b'0:a:999').hexdigest())
        self.assertEqual(file_row['pss_lower_kib'], 200000)
        self.assertEqual(file_row['by_role_pss_lower_kib'], {
            'nox-ds41-8098': 100000, 'nox-dispatcher-t855u': 100000})
        self.assertFalse(file_row['shmem_hint'])
        self.assertTrue(shmem_row['shmem_hint'])
        rendered = json.dumps(receipt)
        for private in ('/private', 'DO_NOT_EXPORT', 'PRIVATE_MEMFD', '00:0a', '199990'):
            self.assertNotIn(private, rendered)

    def test_stale_worker_birth_holds_without_partial_metrics(self):
        self.roles[202] = ('worker_runtime', 2001)
        self.assert_hold(self.run_capture(), 'HOLD_ATTRIBUTION_ROLE_BIRTH_CHANGED')

    def test_changed_maps_do_not_publish_partial_aggregates(self):
        target = self.proc / '202' / 'smaps'
        target.write_bytes(self.smaps.replace(self.file_map, self.file_map.replace(b'999', b'997')))
        self.assert_hold(self.run_capture(), 'HOLD_ATTRIBUTION_MAP_LAYOUT_CHANGED')

    def test_changed_member_set_does_not_publish_partial_aggregates(self):
        initial = iter((True, False))
        def roles():
            if not next(initial):
                self.add_proc(303, 3003)
                (self.group / 'cgroup.procs').write_text('101\n202\n303\n')
            return 101, dict(self.roles)
        self.assert_hold(self.run_capture(roles), 'HOLD_ATTRIBUTION_SNAPSHOT_CHANGED')

    def test_missing_small_inode_metadata_does_not_count_as_inspected(self):
        (self.proc / '101' / 'smaps_rollup').write_bytes(
            b'Pss: 7 kB\nPss_Anon: 5 kB\nPss_File: 2 kB\nPss_Shmem: 0 kB\n')
        (self.proc / '101' / 'smaps').unlink()
        receipt = self.run_capture()
        self.assertEqual(receipt['state'], 'OBSERVED')
        self.assertEqual(receipt['inode_scanned_members'], 1)
        self.assertEqual(receipt['by_role']['nox-dispatcher-t855u']['pss_file_kib'], 2)

    def test_bounded_reads_hold_without_partial_metrics(self):
        with patch.object(inspect, 'ATTRIBUTION_MAX_SMAPS_TOTAL', 64):
            self.assert_hold(self.run_capture(), 'HOLD_ATTRIBUTION_SMAPS_BOUND')

    def test_stale_native_roles_refuse_before_scanning(self):
        result = SimpleNamespace(returncode=0, stdout=(
            'nox-dispatcher-t855u RUNNING pid 101, uptime 0:00:01\n'
            'nox-ds41-8098 RUNNING pid 202, uptime 0:00:01\n'))
        doc = {'native_subexecutors': {'observed_at': 1}}
        with patch.object(inspect.subprocess, 'run', return_value=result), \
             patch.object(inspect, 'obj', return_value=(doc, b'', None)):
            with self.assertRaisesRegex(inspect.CgroupPinHold, '^ATTRIBUTION_STALE_ROLES$'):
                inspect._attribution_roles(now=60)


if __name__ == '__main__':
    unittest.main(verbosity=2)
