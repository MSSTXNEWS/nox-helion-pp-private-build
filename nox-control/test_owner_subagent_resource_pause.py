"""Regression tests for resource-hold scheduling pause and fresh recovery."""
from threading import RLock
import time
import unittest
from unittest.mock import Mock, patch

import owner_autonomy_pool as autonomy
import owner_subagent_dispatcher_fresh as dispatcher
from owner_subagent_processes import GateError, Subagents


class ResourcePauseTests(unittest.TestCase):
    def resource_snapshot(self, **overrides):
        value = {
            'native_verified': True, 'instance_id': 60509551, 'stop_active': False,
            'source_sha_verified': True, 'owner_scope_verified': True, 'task_status': {},
            'cgroup_memory_ratio': .4, 'cpu_pressure': 0.0, 'io_pressure': 0.0,
            'disk_free_ratio': .5, 'disk_free_bytes': 10_000_000_000,
            'disk_total_bytes': 20_000_000_000,
            'resource_admission_allowed': True,
            'resource_admission_observed_at': time.time(),
        }
        value.update(overrides)
        value['resource_admission_snapshot_sha256'] = autonomy.fingerprint(value)
        return value

    def test_only_real_resource_hold_calls_pause_and_fresh_gate_recovers(self):
        native = Mock()
        native.read_reviewed_catalog.return_value = {'schema': autonomy.SCHEMA, 'tasks': []}
        native.read_resource_snapshot.side_effect = [
            autonomy.AutoHold('HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'),
            self.resource_snapshot(),
        ]
        native.allowed_handlers.return_value = set()
        native.owner_allowed.return_value = True
        native.stop_active.return_value = False
        native.writer_lease.return_value = True
        native.ensure_processes.return_value = True
        native.process_readback.return_value = [
            {'pid': 31 + i, 'process_starttime': 100 + i,
             'native_pid_verified': True, 'state': 'RUNNING',
             'instance_id': 60509551, 'origin': 'existing_onehost',
             'native_heartbeat_verified': True, 'heartbeat_age_seconds': 1}
            for i in range(3)
        ]
        native.native_duplicate_check.return_value = False
        native.s03_readback.return_value = {}
        paused = {'value': False}
        def pause(reason):
            self.assertEqual(reason, 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE')
            paused['value'] = True
            return True
        def ensure(count):
            self.assertEqual(count, 3)
            self.assertTrue(paused['value'])
            paused['value'] = False
            return True
        native.pause_for_resource_hold.side_effect = pause
        native.ensure_processes.side_effect = ensure

        first = autonomy.tick_existing_dispatcher(
            {'_nox_owner_autonomy_native': native}, {'tasks': {}}, mode='NORMAL')
        self.assertEqual(first['state'], 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE')
        native.pause_for_resource_hold.assert_called_once()
        native.ensure_processes.assert_not_called()
        self.assertTrue(paused['value'])

        second = autonomy.tick_existing_dispatcher(
            {'_nox_owner_autonomy_native': native}, {}, mode='NORMAL')
        self.assertEqual(second['state'], 'NATIVE_POOL_READY_IDLE')
        self.assertEqual(native.ensure_processes.call_count, 1)
        self.assertFalse(paused['value'])

    def test_worker_pool_pause_blocks_submit_and_dead_worker_respawn(self):
        pool = object.__new__(Subagents)
        pool._abi_lock = RLock()
        pool._resource_paused = True
        pool._persistent = True
        pool._persistent_task = lambda task: None
        pool._submitted_ids = set()
        pool._terminal_ids = set()
        task = {'id': 'task.1', 'subagent': 'runtime', 'task': 'bounded review',
                'depends_on': [], '_native_context': {}}
        with patch.object(pool, '_replace_idle_dead_pool',
                          side_effect=AssertionError('respawn path called')) as respawn:
            with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESOURCE_PAUSED'):
                pool.submit(task)
            respawn.assert_not_called()

        pool.processes = {'runtime': Mock(is_alive=Mock(return_value=False))}
        pool._new_channels = Mock()
        pool._start_workers = Mock()
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESOURCE_PAUSED'):
            pool._replace_idle_dead_pool()
        pool._new_channels.assert_not_called()
        pool._start_workers.assert_not_called()

        self.assertTrue(pool.resume_scheduling())
        self.assertFalse(pool._resource_paused)

    def test_denied_or_stale_readback_does_not_resume(self):
        native = object.__new__(dispatcher.Native)
        native.lock = RLock()
        native.resource_pause_reason = 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'
        native.pool = Mock()
        native.pool.resume_scheduling.return_value = True
        native.last_admission_snapshot = None
        denied = self.resource_snapshot(cgroup_memory_ratio=.96)
        native.read_resource_snapshot = lambda *_args, **_kwargs: denied

        reason = native._fresh_admission_reason()
        self.assertEqual(reason, 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE')
        self.assertEqual(native.resource_pause_reason,
                         'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE')
        native.pool.resume_scheduling.assert_not_called()

        stale = self.resource_snapshot(resource_admission_observed_at=time.time()-10)
        native.read_resource_snapshot = lambda *_args, **_kwargs: stale
        self.assertEqual(native._fresh_admission_reason(),
                         'HOLD_NATIVE_SUBAGENT_ADMISSION')
        self.assertEqual(native.resource_pause_reason,
                         'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE')
        native.pool.resume_scheduling.assert_not_called()

        native.read_resource_snapshot = lambda *_args, **_kwargs: self.resource_snapshot()
        self.assertIsNone(native._fresh_admission_reason())
        self.assertIsNone(native.resource_pause_reason)
        native.pool.resume_scheduling.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
