"""Bounded read-only cgroup pins for owner-inspect process receipts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('owner_native_inspect.py')
SPEC = importlib.util.spec_from_file_location('owner_inspect_cgroup_pin', MODULE)
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


class CgroupPinReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.proc = base / 'proc'
        self.cgroups = base / 'sys/fs/cgroup'
        self.cgroups.mkdir(parents=True)
        (self.cgroups / 'cgroup.controllers').write_text('cpu memory\n')
        self.target_path = '/system.slice/nox.scope'
        self.target = self.cgroups / 'system.slice' / 'nox.scope'
        self.target.mkdir(parents=True)
        (self.target / 'cgroup.type').write_text('domain\n')
        (self.target / 'memory.reclaim').write_text('')

    @staticmethod
    def _stat(pid, ppid, start_ticks):
        fields = ['S', str(ppid), str(ppid)] + ['0'] * 16 + [str(start_ticks)]
        return f'{pid} (nox worker) ' + ' '.join(fields) + '\n'

    def add_proc(self, pid, start_ticks, *, cgroup_path=None, ppid=1):
        directory = self.proc / str(pid)
        directory.mkdir(parents=True)
        (directory / 'stat').write_text(self._stat(pid, ppid, start_ticks))
        (directory / 'cgroup').write_text(
            '0::' + (self.target_path if cgroup_path is None else cgroup_path) + '\n')
        return directory

    def pin(self, pid=101, start_ticks=1001):
        return INSPECT.cgroup_process_pin(
            pid, start_ticks, proc_root=self.proc, cgroup_root=self.cgroups)

    def test_emits_complete_leaf_pin_and_helper_compatible_hash(self):
        self.add_proc(101, 1001)
        self.add_proc(202, 2002)
        # Kernel enumeration order is not the canonical pin order.
        (self.target / 'cgroup.procs').write_text('202\n101\n')
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'PINNED_READ_ONLY')
        self.assertEqual(receipt['cgroup_path'], self.target_path)
        self.assertEqual(receipt['device'], self.target.stat().st_dev)
        self.assertEqual(receipt['inode'], self.target.stat().st_ino)
        self.assertEqual(receipt['cgroup_type'], 'domain')
        self.assertTrue(receipt['members_complete'])
        self.assertEqual(receipt['member_count'], 2)
        self.assertEqual(receipt['members'], [
            {'pid': 101, 'start_ticks': 1001},
            {'pid': 202, 'start_ticks': 2002},
        ])
        self.assertEqual(receipt['child_count'], 0)
        self.assertTrue(receipt['children_complete'])
        self.assertTrue(receipt['leaf_cgroup'])
        self.assertTrue(receipt['memory_reclaim_present'])
        pin = {'cgroup_path': receipt['cgroup_path'],
               'device': receipt['device'], 'inode': receipt['inode'],
               'members': receipt['members']}
        expected = INSPECT.hashlib.sha256(json.dumps(
            pin, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(receipt['pin_sha256'], expected)
        self.assertTrue(receipt['read_only'])

    def test_child_cgroup_is_counted_and_target_is_held(self):
        self.add_proc(101, 1001)
        (self.target / 'cgroup.procs').write_text('101\n')
        (self.target / 'child').mkdir()
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_NOT_LEAF')
        self.assertEqual(receipt['child_count'], 1)
        self.assertFalse(receipt['leaf_cgroup'])
        self.assertTrue(receipt['members_complete'])
        self.assertIsNone(receipt['pin_sha256'])

    def test_process_member_must_match_exact_unified_path(self):
        self.add_proc(101, 1001)
        self.add_proc(202, 2002, cgroup_path='/other.scope')
        (self.target / 'cgroup.procs').write_text('101\n202\n')
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_MEMBER_PATH_CHANGED')
        self.assertFalse(receipt['members_complete'])
        self.assertEqual(receipt['members'], [])

    def test_cgroup_target_symlink_is_rejected(self):
        self.add_proc(101, 1001)
        (self.target / 'cgroup.procs').write_text('101\n')
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        real_target = self.target.with_name('nox.scope.real')
        self.target.rename(real_target)
        self.target.symlink_to(outside, target_is_directory=True)
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_PATH')
        self.assertIsNone(receipt['cgroup_path'])

    def test_incomplete_member_set_fails_closed_at_helper_limit(self):
        self.add_proc(101, 1001)
        (self.target / 'cgroup.procs').write_text(
            ''.join(f'{pid}\n' for pid in range(101, 230)))
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_MEMBER_LIMIT')
        self.assertEqual(receipt['member_count'], 129)
        self.assertFalse(receipt['members_complete'])
        self.assertEqual(receipt['members'], [])

    def test_root_cgroup_is_reported_but_never_a_target_pin(self):
        self.add_proc(101, 1001, cgroup_path='/')
        (self.cgroups / 'cgroup.type').write_text('domain\n')
        (self.cgroups / 'cgroup.procs').write_text('101\n')
        (self.cgroups / 'memory.reclaim').write_text('')
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_ROOT_NOT_TARGETABLE')
        self.assertEqual(receipt['cgroup_path'], '/')
        self.assertTrue(receipt['members_complete'])
        self.assertTrue(receipt['read_only'])

    def test_claimed_process_start_ticks_are_required(self):
        self.add_proc(101, 1002)
        (self.target / 'cgroup.procs').write_text('101\n')
        receipt = self.pin(start_ticks=1001)
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_PROCESS_IDENTITY_CHANGED')
        self.assertFalse(receipt['members_complete'])

    def test_process_receipt_attaches_pin_only_to_matching_claim(self):
        process = self.add_proc(101, 1001, ppid=7)
        (process / 'status').write_text('NSpid:\t101\n')
        (process / 'environ').write_bytes(b'NOX_DISPATCHER_SAFE=1\0')
        (self.target / 'cgroup.procs').write_text('101\n')
        from unittest.mock import patch
        with patch.object(INSPECT, 'PROC', self.proc), \
             patch.object(INSPECT, 'CGROUP_ROOT', self.cgroups):
            observed = INSPECT.process(
                101, include_cgroup=True,
                expected_start_ticks=1001, expected_ppid=7)
            stale = INSPECT.process(
                101, include_cgroup=True,
                expected_start_ticks=1000, expected_ppid=7)
        self.assertEqual(observed['cgroup_pin']['state'], 'PINNED_READ_ONLY')
        self.assertEqual(observed['cgroup_pin']['process_pid'], 101)
        self.assertEqual(stale['status'], 'UNKNOWN_OR_CHANGED')
        self.assertNotIn('cgroup_pin', stale)

    def test_missing_memory_reclaim_entry_is_not_helper_eligible(self):
        self.add_proc(101, 1001)
        (self.target / 'cgroup.procs').write_text('101\n')
        (self.target / 'memory.reclaim').unlink()
        receipt = self.pin()
        self.assertEqual(receipt['state'], 'HOLD_CGROUP_MEMORY_RECLAIM_ABSENT')
        self.assertTrue(receipt['members_complete'])
        self.assertFalse(receipt['memory_reclaim_present'])
        self.assertIsNone(receipt['pin_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
