"""Regression tests for explicit, PID-bound lock observations; no host I/O."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name('owner_systemic_relay_observe.py')
SPEC = importlib.util.spec_from_file_location('relay_observer_under_test', MODULE)
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


class LockObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock_path = self.root / 'owner_maintenance.lock'
        self.lock_path.write_text('')
        self.proc_root = self.root / 'proc'
        self.proc_root.mkdir()
        self.boot_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        boot_id_path = self.proc_root / 'sys/kernel/random/boot_id'
        boot_id_path.parent.mkdir(parents=True)
        boot_id_path.write_text(self.boot_id + '\n')
        self.proc_uptime = self.proc_root / 'uptime'
        self.proc_uptime.write_text('12345.25 54321.00\n')
        self.pid = 424242
        self._write_process(self.pid, start_ticks=123456)
        self.proc_locks = self.root / 'locks'
        self.proc_locks.write_text(self._lock_line(self.pid))

    def _write_process(self, pid, *, start_ticks, ppid=1):
        proc = self.proc_root / str(pid)
        proc.mkdir(exist_ok=True)
        suffix = ['S', str(ppid)] + ['0'] * 17 + [str(start_ticks)]
        (proc / 'stat').write_text(f'{pid} (python worker) ' + ' '.join(suffix))
        (proc / 'comm').write_text('python3\n')
        (proc / 'cmdline').write_bytes(b'python3\0/root/nox/scripts/worker.py\0secret-arg\0')
        (proc / 'status').write_text('Name:\tpython3\nUid:\t0\t0\t0\t0\n')
        (proc / 'exe').symlink_to('/usr/bin/python3')

    def _lock_line(self, pid):
        info = self.lock_path.stat()
        return (f'4: FLOCK ADVISORY WRITE {pid} '
                f'{os.major(info.st_dev):x}:{os.minor(info.st_dev):x}:{info.st_ino} 0 EOF\n')

    def _observe(self, lock_source=None):
        return INSPECT.locks(
            proc_locks_path=lock_source or self.proc_locks,
            lock_paths=(self.lock_path,), proc_root=self.proc_root)[0]

    def test_matching_lock_resolves_stable_pid_and_safe_command_projection(self):
        row = self._observe()
        self.assertEqual(row['proc_locks_read_status'], 'READ_OK')
        self.assertEqual(row['matching_lock_count'], 1)
        self.assertEqual(row['matching_kernel_locks'][0].split()[1], 'FLOCK')
        self.assertTrue(row['lock_observation_complete'])
        holder = row['matching_lock_records'][0]['holder_identity']
        self.assertEqual(holder['pid'], self.pid)
        self.assertEqual(holder['start_ticks'], 123456)
        self.assertEqual(holder['ppid'], 1)
        self.assertEqual(holder['command'], 'python3 worker.py')
        self.assertNotIn('secret-arg', holder['command'])
        self.assertEqual(row['holder_identity_recheck_status'], 'STABLE')
        self.assertEqual(row['matching_lock_records'][0]['holder_identity_recheck'],
                         'STABLE')
        self.assertEqual(row['host_clock_snapshot_status'], 'STABLE')
        host_clock = row['host_clock_snapshot']['final']
        self.assertEqual(host_clock['boot_id'], self.boot_id)
        self.assertEqual(host_clock['uptime_seconds'], 12345.25)
        self.assertEqual(host_clock['sc_clk_tck'], os.sysconf('SC_CLK_TCK'))
        self.assertEqual(holder['host_boot_id'], self.boot_id)
        self.assertEqual(holder['host_clock_snapshot_sha256'], host_clock['snapshot_sha256'])
        self.assertAlmostEqual(holder['process_start_epoch_unix_estimate'],
            host_clock['boot_epoch_unix_estimate'] + 123456 / host_clock['sc_clk_tck'])
        self.assertEqual(row['holder_identity_rechecks'][0]['host_clock_snapshot_sha256'],
                         host_clock['snapshot_sha256'])

    def test_host_clock_unavailable_fails_closed(self):
        self.proc_uptime.unlink()
        row = self._observe()
        self.assertEqual(row['host_clock_snapshot_status'], 'UNAVAILABLE')
        self.assertEqual(row['host_clock_snapshot']['final']['status'], 'UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_clk_tck_unavailable_fails_closed(self):
        with patch.object(INSPECT.os, 'sysconf', side_effect=OSError('clock tick rate unavailable')):
            row = self._observe()
        self.assertEqual(row['host_clock_snapshot_status'], 'UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_boot_id_change_during_observation_fails_closed(self):
        real_read = INSPECT._read_proc_locks
        read_count = 0
        boot_id_path = self.proc_root / 'sys/kernel/random/boot_id'

        def read_locks(path):
            nonlocal read_count
            read_count += 1
            result = real_read(path)
            if read_count == 2:
                boot_id_path.write_text('bbbbbbbb-cccc-dddd-eeee-ffffffffffff\n')
            return result

        with patch.object(INSPECT, '_read_proc_locks', side_effect=read_locks):
            row = self._observe()

        self.assertEqual(row['host_clock_snapshot_status'], 'BOOT_ID_CHANGED')
        self.assertEqual(row['host_clock_snapshot']['initial']['boot_id'], self.boot_id)
        self.assertEqual(row['host_clock_snapshot']['final']['boot_id'],
                         'bbbbbbbb-cccc-dddd-eeee-ffffffffffff')
        self.assertEqual(row['holder_identity_recheck_status'], 'CHANGED_OR_UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_boot_change_between_subsnapshots_fails_closed_for_whole_inspection(self):
        first = {'status':'VERIFIED', 'boot_id':self.boot_id, 'uptime_seconds':10.0,
                 'sc_clk_tck':100, 'observed_at_unix':200.0,
                 'boot_epoch_unix_estimate':190.0, 'snapshot_sha256':'a'*64}
        second = {**first, 'boot_id':'bbbbbbbb-cccc-dddd-eeee-ffffffffffff',
                  'uptime_seconds':2.0, 'observed_at_unix':500.0,
                  'boot_epoch_unix_estimate':498.0, 'snapshot_sha256':'b'*64}
        a={'status':'STABLE','initial':first,'final':first}
        b={'status':'STABLE','initial':second,'final':second}
        self.assertEqual(INSPECT._host_clock_chain_status((a,b)), 'BOOT_ID_CHANGED')

    def test_proc_locks_read_failure_is_not_reported_as_no_active_locks(self):
        row = self._observe(self.root / 'not-readable')
        self.assertEqual(row['proc_locks_read_status'], 'UNAVAILABLE')
        self.assertEqual(row['matching_lock_count'], 0)
        self.assertFalse(row['lock_observation_complete'])
        self.assertIn('proc_locks_error', row)

    def test_pid_reuse_during_mapping_fails_closed(self):
        with patch.object(INSPECT, '_proc_stat_identity', side_effect=[
                {'pid':self.pid, 'ppid':1, 'state':'S', 'start_ticks':123456},
                {'pid':self.pid, 'ppid':1, 'state':'S', 'start_ticks':123457}]):
            identity = INSPECT.process_identity(self.pid, self.proc_root)
        self.assertEqual(identity['resolution'], 'UNKNOWN_OR_CHANGED')

    def test_open_file_description_lock_reports_owner_pid_unavailable(self):
        self.proc_locks.write_text(self._lock_line(-1))
        row = self._observe()
        self.assertEqual(row['matching_lock_records'][0]['pid_kind'],
                         'OPEN_FILE_DESCRIPTION_OR_UNKNOWN')
        self.assertEqual(row['matching_lock_records'][0]['holder_identity']['resolution'],
                         'PID_NOT_EXPOSED_BY_PROC_LOCKS')
        self.assertFalse(row['lock_observation_complete'])

    def test_no_matching_lock_is_explicitly_complete_only_after_readback(self):
        self.proc_locks.write_text('5: FLOCK ADVISORY WRITE 999 00:01:888 0 EOF\n')
        row = self._observe()
        self.assertEqual(row['proc_locks_read_status'], 'READ_OK')
        self.assertEqual(row['matching_lock_count'], 0)
        self.assertTrue(row['lock_observation_complete'])

    def test_kernel_lock_churn_during_pid_resolution_fails_closed(self):
        original = self.proc_locks.read_text()
        first = {'status':'READ_OK', 'raw':original, 'lines':original.splitlines(),
                 'truncated':False, 'error':None}
        changed = original.replace('WRITE', 'READ')
        second = {'status':'READ_OK', 'raw':changed, 'lines':changed.splitlines(),
                  'truncated':False, 'error':None}
        with patch.object(INSPECT, '_read_proc_locks', side_effect=(first, second)):
            row = self._observe()
        self.assertEqual(row['proc_locks_stability'], 'CHANGED_OR_UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_holder_identity_change_after_final_locks_read_fails_closed(self):
        real_read = INSPECT._read_proc_locks
        stable_identity = INSPECT.process_identity(self.pid, self.proc_root)
        changed_identity = {**stable_identity, 'comm':'replaced-worker',
                            'command':'python3 replaced.py'}
        identities = [stable_identity, changed_identity]
        events = []

        def read_locks(path):
            events.append('locks')
            return real_read(path)

        def read_identity(pid, proc_root):
            events.append('identity')
            return identities.pop(0)

        with patch.object(INSPECT, '_read_proc_locks', side_effect=read_locks), \
                patch.object(INSPECT, 'process_identity', side_effect=read_identity):
            row = self._observe()

        self.assertEqual(events, ['locks', 'identity', 'locks', 'identity'])
        self.assertEqual(row['holder_identity_recheck_status'], 'CHANGED_OR_UNAVAILABLE')
        self.assertEqual(row['holder_identity_rechecks'][0]['before']['comm'], 'python3')
        self.assertEqual(row['holder_identity_rechecks'][0]['after']['comm'],
                         'replaced-worker')
        self.assertEqual(row['matching_lock_records'][0]['holder_identity_recheck'],
                         'CHANGED_OR_UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])


if __name__ == '__main__':
    unittest.main()
