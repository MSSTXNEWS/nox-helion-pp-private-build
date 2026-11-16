"""Synthetic files and metadata only; never hash a native model or start it."""
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import owner_hermes_ram_preflight as probe


class HermesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ssd = self.root / 'ssd/teachers/model.gguf'
        self.warm = self.root / 'ram/teachers/model.gguf'
        self.teacher = self.root / 'models/teachers/model.gguf'
        for p in (self.ssd, self.warm, self.teacher): p.parent.mkdir(parents=True)
        self.raw = b'SYNTHETIC_GGUF' * 8192; self.ssd.write_bytes(self.raw); self.ssd.chmod(0o666)
        self.warm.symlink_to(self.ssd); self.teacher.symlink_to(self.warm)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for key, value in {'ROOT': self.root, 'SSD': self.ssd, 'WARM': self.warm, 'TEACHER': self.teacher,
                'SIZE': len(self.raw), 'SHA': hashlib.sha256(self.raw).hexdigest(), 'RATE': 10**12}.items():
            self.stack.enter_context(patch.object(probe, key, value))

    def test_full_hash_same_fd_named_identity_and_no_model_content_export(self):
        fd = probe.open_plain(self.ssd)
        try:
            result = {}; expected = probe.identity(os.fstat(fd))
            self.assertEqual(probe.full_hash(fd, time.monotonic() + 2, result), expected)
            self.assertEqual(result, {'ssd_bytes_read': len(self.raw)})
        finally: os.close(fd)
        self.assertEqual(self.ssd.read_bytes(), self.raw)

    def test_corruption_and_name_replacement_do_not_pass_full_sha(self):
        self.ssd.write_bytes(b'X' + self.raw[1:]); fd = probe.open_plain(self.ssd)
        try:
            with self.assertRaisesRegex(probe.Hold, 'SSD_FULL_SHA_OR_IDENTITY'):
                probe.full_hash(fd, time.monotonic() + 2, {})
        finally: os.close(fd)
        self.ssd.write_bytes(self.raw); fd = probe.open_plain(self.ssd)
        replacement = self.ssd.parent / 'new'; replacement.write_bytes(self.raw); os.replace(replacement, self.ssd)
        try:
            with self.assertRaisesRegex(probe.Hold, 'SSD_NAME_CHANGED'):
                probe.full_hash(fd, time.monotonic() + 2, {})
        finally: os.close(fd)

    def test_known_aliases_report_one_ssd_copy_and_preserve_all_names(self):
        before = {p: p.lstat() for p in (self.ssd, self.warm, self.teacher)}
        rows = probe.aliases(probe.identity(self.ssd.stat()))
        self.assertTrue(all(r['same_ssd_inode'] for r in rows.values()))
        self.assertEqual(rows['LEGACY_TEACHER_ALIAS']['symlink_hops'], 2)
        self.assertFalse(rows['RAM_WARM_ALIAS']['independent_full_copy_verified'])
        self.assertEqual(len(rows['RAM_WARM_ALIAS']['link_metadata']), 1)
        self.assertNotIn(str(self.root), json.dumps(rows))
        for p, info in before.items(): self.assertEqual(probe.identity(p.lstat()), probe.identity(info))

    def test_unknown_target_and_loop_are_not_followed_as_verified_aliases(self):
        private = self.root / 'PRIVATE_UNRELATED'; private.write_bytes(b'PRIVATE CONTENT')
        self.warm.unlink(); self.warm.symlink_to(private)
        rows = probe.aliases(probe.identity(self.ssd.stat()))
        self.assertEqual(rows['RAM_WARM_ALIAS']['state'], 'ALIAS_UNVERIFIED')
        self.assertNotIn('PRIVATE_UNRELATED', json.dumps(rows))
        self.warm.unlink(); self.warm.symlink_to(self.teacher)
        rows = probe.aliases(probe.identity(self.ssd.stat()))
        self.assertIn('ALIAS_HOPS', rows['RAM_WARM_ALIAS']['reason'])

    def test_inspection_read_only_and_partial_visibility_never_claims_unused(self):
        budget = {'cgroup_limit_bytes': 194065203200, 'cgroup_peak_bytes': 174986956800,
                  'cgroup_headroom_bytes': 108552454144, 'tmpfs_free_bytes': 7983484928, 'dev_shm_is_tmpfs': True}
        profile = {name: {'source_matches': True} for name in probe.PROFILE_PINS}
        before = {p: (probe.identity(p.lstat()), p.readlink() if p.is_symlink() else p.read_bytes())
                  for p in (self.ssd, self.warm, self.teacher)}
        with patch.object(probe, 'proc_helper', return_value=None), patch.object(probe, 'budget', return_value=budget), \
             patch.object(probe, 'source_roles', return_value=profile), patch.object(probe, 'services', return_value={}), \
             patch.object(probe, 'process_refs', return_value={'complete': False, 'known_reference_count': 0,
                  'partial_visibility_is_not_inactivity_proof': True}):
            result = probe.inspect()
        self.assertEqual(result['state'], 'HERMES_IDENTITY_AND_RESOURCES_OBSERVED')
        self.assertTrue(result['full_current_ssd_sha_verified'])
        self.assertFalse(result['migration_authorized'])
        self.assertFalse(result['process_scan_after']['complete'])
        self.assertEqual(result['files_written'], 0)
        for p, value in before.items():
            self.assertEqual((probe.identity(p.lstat()), p.readlink() if p.is_symlink() else p.read_bytes()), value)

    def test_symlink_ssd_cannot_be_hashed_through_unreviewed_target(self):
        actual = self.ssd.with_name('actual'); self.ssd.rename(actual); self.ssd.symlink_to(actual)
        with self.assertRaises(OSError): probe.open_plain(self.ssd)


class BudgetAndSourceTests(unittest.TestCase):
    def test_historical_peak_and_actual_qwen_gates_are_separate_not_weakened(self):
        row = {'cgroup_limit_bytes': 194065203200, 'cgroup_peak_bytes': 174986956800,
               'cgroup_headroom_bytes': 108552454144, 'tmpfs_free_bytes': 7983484928, 'dev_shm_is_tmpfs': True}
        result = probe.projections(row, True)
        self.assertEqual(result['conservative_lifetime_peak_budget_bytes'], 1898377216)
        self.assertFalse(result['conservative_lifetime_peak_fits'])
        self.assertFalse(result['tmpfs_reserve_fits'])
        self.assertEqual(result['qwen_initial_stage_required_headroom_bytes'], 70869001213)
        self.assertEqual(result['qwen_post_base_required_headroom_bytes'], 40 * 1024**3)
        self.assertTrue(result['projected_qwen_initial_stage_gate_fits'])
        self.assertTrue(result['projected_qwen_post_base_gate_fits'])
        self.assertFalse(result['migration_or_training_start_authorized'])
        self.assertFalse(probe.projections(row, False)['projected_qwen_initial_stage_gate_fits'])

    def test_missing_tmpfs_or_tight_current_headroom_never_admitted_by_peak(self):
        row = {'cgroup_limit_bytes': 200 * probe.GIB, 'cgroup_peak_bytes': 100 * probe.GIB,
               'cgroup_headroom_bytes': 65 * probe.GIB, 'tmpfs_free_bytes': 10 * probe.GIB, 'dev_shm_is_tmpfs': False}
        result = probe.projections(row, True)
        self.assertFalse(result['tmpfs_reserve_fits'])
        self.assertFalse(result['projected_qwen_initial_stage_gate_fits'])

    def test_proc_helper_source_checked_before_execution(self):
        raw = Path(__file__).with_name(probe.PROC_NAME).read_bytes()
        with patch.object(probe, 'BUNDLE', {probe.PROC_NAME: base64.b64encode(raw).decode()}):
            self.assertTrue(callable(probe.proc_helper().probe_process))
        with patch.object(probe, 'BUNDLE', {probe.PROC_NAME: base64.b64encode(b'raise AssertionError()').decode()}):
            with self.assertRaisesRegex(probe.Hold, 'PROC_SOURCE_PIN'): probe.proc_helper()


if __name__ == '__main__': unittest.main()
