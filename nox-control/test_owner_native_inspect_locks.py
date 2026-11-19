"""Synthetic regression tests for native owner lock/boot identity output.

All files are temporary and all remote/host operations are stubbed. No native
NOX server, STOP flag, lock file, service, SSH credential, or receipt is read.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INSPECT = load_module('owner_native_inspect_locks_under_test',
                      HERE / 'owner_native_inspect.py')
OPERATOR = load_module('owner_native_operator_route_under_test',
                       HERE / 'owner_native_operator.py')
SCOPED_OPERATOR = load_module('owner_native_operator_scoped_route_under_test',
                              HERE / 'owner_native_operator_scoped_bundle.py')


class NativeLockInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proc_root = self.root / 'proc'
        self.proc_root.mkdir()
        self.boot_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        boot_path = self.proc_root / 'sys/kernel/random/boot_id'
        boot_path.parent.mkdir(parents=True)
        boot_path.write_text(self.boot_id + '\n')
        self.uptime_path = self.proc_root / 'uptime'
        self.uptime_path.write_text('12345.25 54321.00\n')
        self.lock_path = self.root / 'owner_maintenance.lock'
        self.lock_path.write_text('')
        self.proc_locks = self.root / 'locks'
        self.pid = 424242
        self._write_process(self.pid, start_ticks=123456)
        self.proc_locks.write_text(self._lock_line(self.pid))

    def _write_process(self, pid, *, start_ticks, ppid=1, comm='python worker',
                       command=b'/usr/bin/python3\0/root/nox/scripts/worker.py\0secret-arg\0'):
        proc = self.proc_root / str(pid)
        proc.mkdir(exist_ok=True)
        suffix = ['S', str(ppid)] + ['0'] * 17 + [str(start_ticks)]
        (proc / 'stat').write_text(f'{pid} ({comm}) ' + ' '.join(suffix))
        (proc / 'comm').write_text('python3\n')
        (proc / 'cmdline').write_bytes(command)
        (proc / 'status').write_text('Name:\tpython3\nUid:\t0\t0\t0\t0\n')
        exe = proc / 'exe'
        if exe.exists() or exe.is_symlink():
            exe.unlink()
        exe.symlink_to('/usr/bin/python3')

    def _lock_line(self, pid):
        info = self.lock_path.stat()
        return (f'4: FLOCK ADVISORY WRITE {pid} '
                f'{os.major(info.st_dev):x}:{os.minor(info.st_dev):x}:{info.st_ino} 0 EOF\n')

    def _locks(self, **kwargs):
        return INSPECT.locks(proc_locks_path=self.proc_locks,
            lock_paths=(self.lock_path,), proc_root=self.proc_root, **kwargs)

    def _clock(self, *, boot_id=None, uptime=12345.25):
        boot_id = self.boot_id if boot_id is None else boot_id
        ticks = os.sysconf('SC_CLK_TCK')
        now = 1800000000.0 + uptime
        record = {'boot_id':boot_id, 'uptime_seconds':uptime, 'sc_clk_tck':ticks,
                  'observed_at_unix':now, 'boot_epoch_unix_estimate':now-uptime}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return {'status':'VERIFIED', **record, 'snapshot_sha256':digest}

    def test_lock_record_contains_file_holder_clock_and_start_epoch_bindings(self):
        row = self._locks()[0]
        self.assertEqual(row['proc_locks_read_status'], 'READ_OK')
        self.assertEqual(row['proc_locks_stability'], 'STABLE')
        self.assertTrue(row['lock_observation_complete'])
        record = row['matching_lock_records'][0]
        holder = record['holder_identity']
        self.assertEqual(holder['pid'], self.pid)
        self.assertEqual(holder['start_ticks'], 123456)
        self.assertEqual(holder['comm'], 'python3')
        self.assertEqual(holder['command'], 'python3 worker.py')
        self.assertNotIn('secret-arg', json.dumps(row))
        self.assertEqual(record['holder_identity_recheck'], 'STABLE')
        clock = row['host_clock_snapshot']['final']
        self.assertEqual(row['host_clock_snapshot_status'], 'STABLE')
        self.assertEqual(clock['boot_id'], self.boot_id)
        self.assertEqual(clock['uptime_seconds'], 12345.25)
        self.assertEqual(clock['sc_clk_tck'], os.sysconf('SC_CLK_TCK'))
        self.assertEqual(holder['host_boot_id'], self.boot_id)
        self.assertEqual(holder['host_clock_snapshot_sha256'], clock['snapshot_sha256'])
        self.assertAlmostEqual(holder['process_start_epoch_unix_estimate'],
            clock['boot_epoch_unix_estimate'] + 123456 / clock['sc_clk_tck'])

    def test_recheck_after_second_locks_read_detects_pid_identity_change(self):
        initial = INSPECT.process_identity(self.pid, self.proc_root)
        changed = dict(initial, comm='renamed-worker', command='python3 other.py')
        with patch.object(INSPECT, 'process_identity', side_effect=[initial, changed]):
            row = self._locks()[0]
        self.assertEqual(row['proc_locks_recheck_status'], 'READ_OK')
        self.assertEqual(row['holder_identity_recheck_status'], 'CHANGED_OR_UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])
        self.assertEqual(row['matching_lock_records'][0]['holder_identity_recheck'],
                         'CHANGED_OR_UNAVAILABLE')

    def test_boot_id_change_fails_closed(self):
        changed_id = 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff'
        with patch.object(INSPECT, '_host_boot_clock_snapshot',
                          side_effect=[self._clock(), self._clock(boot_id=changed_id)]):
            row = self._locks()[0]
        self.assertEqual(row['host_clock_snapshot_status'], 'BOOT_ID_CHANGED')
        self.assertFalse(row['lock_observation_complete'])
        self.assertEqual(row['holder_identity_rechecks'][0]['status'],
                         'CHANGED_OR_UNAVAILABLE')

    def test_clock_chain_distinguishes_host_reboot(self):
        before = INSPECT._host_clock_pair(
            self._clock(uptime=10.0), self._clock(uptime=11.0))
        after = INSPECT._host_clock_pair(
            self._clock(boot_id='bbbbbbbb-cccc-dddd-eeee-ffffffffffff', uptime=1.0),
            self._clock(boot_id='bbbbbbbb-cccc-dddd-eeee-ffffffffffff', uptime=2.0))
        self.assertEqual(INSPECT._host_clock_chain_status((before, after)),
                         'BOOT_ID_CHANGED')

    def test_missing_clock_basis_fails_closed(self):
        unavailable = {'status':'UNAVAILABLE', 'reason':'FileNotFoundError'}
        with patch.object(INSPECT, '_host_boot_clock_snapshot',
                          side_effect=[self._clock(), unavailable]):
            row = self._locks()[0]
        self.assertEqual(row['host_clock_snapshot_status'], 'UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_unavailable_clock_tick_rate_fails_closed(self):
        with patch.object(INSPECT.os, 'sysconf', side_effect=OSError('clock rate unavailable')):
            row = self._locks()[0]
        self.assertEqual(row['host_clock_snapshot_status'], 'UNAVAILABLE')
        self.assertFalse(row['lock_observation_complete'])

    def test_proc_locks_read_is_bounded(self):
        self.proc_locks.write_text('x' * (INSPECT.MAX_PROC_LOCKS_BYTES + 1))
        row = self._locks()[0]
        self.assertEqual(row['proc_locks_read_status'], 'READ_TRUNCATED')
        self.assertEqual(row['proc_locks_recheck_status'], 'NOT_ATTEMPTED')
        self.assertFalse(row['lock_observation_complete'])

    def test_current_owner_inspect_dispatchers_ship_native_inspector(self):
        expected = 'nox-control/owner_native_inspect.py'
        self.assertEqual(OPERATOR.FILES['inspect'], expected)
        self.assertEqual(SCOPED_OPERATOR.FILES['inspect'], expected)

    def test_main_owner_output_contains_native_lock_fields(self):
        original_locks = INSPECT.locks
        clock_index = 0

        def clock(*_args, **_kwargs):
            nonlocal clock_index
            clock_index += 1
            return self._clock(uptime=12340.0 + clock_index * 20)

        snapshots = [
            {'host_clock_snapshot':INSPECT._host_clock_pair(
                self._clock(uptime=12340.0), self._clock(uptime=12341.0)),
             'services':[], 'snapshot_complete':True},
            {'host_clock_snapshot':INSPECT._host_clock_pair(
                self._clock(uptime=12390.0), self._clock(uptime=12391.0)),
             'services':[], 'snapshot_complete':True},
        ]
        output = io.StringIO()

        def fixture_locks():
            return original_locks(proc_locks_path=self.proc_locks,
                lock_paths=(self.lock_path,), proc_root=self.proc_root)

        with contextlib.redirect_stdout(output), \
             patch.object(INSPECT, 'runtime_snapshot', side_effect=snapshots), \
             patch.object(INSPECT, 'worker_status_sample'), \
             patch.object(INSPECT, 'hash_summary'), \
             patch.object(INSPECT, 'project_summary'), \
             patch.object(INSPECT, 'old_claim_comparison'), \
             patch.object(INSPECT, 'configuration'), \
             patch.object(INSPECT, 'leaf_queue_summary'), \
             patch.object(INSPECT, 'locks', side_effect=fixture_locks), \
             patch.object(INSPECT, '_host_boot_clock_snapshot', side_effect=clock), \
             patch.object(INSPECT.time, 'sleep'):
            INSPECT.main()
        lines = output.getvalue().splitlines()
        lock_line = next(line for line in lines if line.startswith('NOX_MAINT_SCOPE_LOCKS='))
        row = json.loads(lock_line.split('=', 1)[1])[0]
        self.assertEqual(row['host_clock_chain_status'], 'STABLE')
        self.assertTrue(row['lock_observation_complete'])
        self.assertIn('host_boot_id', row['matching_lock_records'][0]['holder_identity'])
        self.assertTrue(any(line.startswith('NOX_MAINT_SCOPE_HOST_CLOCK_CHAIN=')
                            for line in lines))
        self.assertIn('NOX_MAINT_INSPECT_COMPLETE=true', lines)


if __name__ == '__main__':
    unittest.main()
