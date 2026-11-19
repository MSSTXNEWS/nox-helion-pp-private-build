"""Focused invariants for native NOX self-observation.

No host mutation, GPU/model call, queue replay, user secrets or dispatcher.
Run with: python -m unittest test_owner_reflex_cycle
"""
from __future__ import annotations

import importlib.util
import fcntl
import inspect
import os
import tempfile
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parent / 'runtime' / 'owner_systemic_refill.py'
SPEC = importlib.util.spec_from_file_location('owner_refill_under_test', MODULE)
refill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refill)
PIN = 'a' * 64
PARENT = '3A03'
ROOT = 'source_workspace'


def mission(name='cache_fill_ttl', parent=PARENT):
    return {'mission_id': name, 'revision': 1,
        'parent_task_id': parent, 'root_id': ROOT,
        'priority': 'P0', 'queue_id': 'Q1_RUNTIME_CHAT',
        'context': [{'path': 'code/cache.py', 'sha256': PIN}]}


def manifest(missions=None, topics=None):
    return {'registry': {'total_original_ids': 295,
        'parents': {p:{'queue_id':'Q1_RUNTIME_CHAT'}
                    for p in (PARENT,'4A02','3B05')}},
        'missions': missions if missions is not None else [mission()],
        'research_topics': topics if topics is not None else []}


def tick(m=None, state=None, deferred=None, source=None, rows=None):
    return refill._reflex_cycle(
        m or manifest(), state if state is not None else {},
        source if source is not None else {ROOT:{'code/cache.py':PIN}},
        {'manifest_sha256': 'b'*64, 'slots_available':3},
        deferred or [], rows or [])


class NativeReflexTests(unittest.TestCase):
    def test_exhaustion_is_not_fake_job_or_approval(self):
        result = tick()
        self.assertEqual(result['state'], 'REFILL_REQUIRED')
        self.assertEqual(result['new_native_jobs'], 0)
        self.assertFalse(result['automatic_owner_approval'])
        self.assertEqual(result['registry_original_total'],295)
        self.assertEqual(result['unindexed_original_count'],292)
        self.assertEqual(result['staged_count'],0)

    def test_source_drift_creates_pinned_investigation_only(self):
        result = tick(deferred=[{'mission_id':'cache_fill_ttl',
                                 'reason':'SOURCE_PIN_DRIFT_REVIEW_REQUIRED'}])
        self.assertEqual(result['staged_count'],1)
        candidate=result['staged_research_candidates'][0]
        self.assertEqual(candidate['parent_task_id'],PARENT)
        self.assertEqual(candidate['observed_sources'],
                         [{'path':'code/cache.py','observed_sha256':PIN}])
        self.assertFalse(candidate['new_native_job_created'])
        self.assertEqual(candidate['authority'],'RESEARCH_PROPOSAL_ONLY')

    def test_failed_terminal_produces_new_review_not_replay(self):
        result = tick(state={'a':{
            'status':'failed','systemic_relay':{'binding':{
                'mission_id':'cache_fill_ttl','mission_revision':1,
                'input_sha256':'f'*64}}}},
            deferred=[{'mission_id':'cache_fill_ttl','reason':'ALREADY_ADMITTED_NO_REPLAY'}])
        self.assertEqual(result['observed_task_counts']['blocked'],1)
        self.assertEqual(result['staged_count'],1)
        self.assertEqual(result['staged_research_candidates'][0]['hypothesis'],
                         'ANALYZE_FAILED_TERMINAL_RECEIPT')

    def test_completed_terminal_is_never_resubmitted(self):
        result = tick(state={'a':{
            'status':'done','systemic_relay':{'binding':{
                'mission_id':'cache_fill_ttl','mission_revision':1}}}},
            deferred=[{'mission_id':'cache_fill_ttl','reason':'ALREADY_ADMITTED_NO_REPLAY'}])
        self.assertEqual(result['staged_count'],0)
        self.assertEqual(result['new_native_jobs'],0)

    def test_research_topics_are_not_automatic_native_jobs(self):
        result = tick(m=manifest(topics=[
            {'parent_task_id':'4A02','objective':'Ground one S03 source defect'},
            {'parent_task_id':'3B05','objective':'Measure the real model latency'}]))
        self.assertEqual(result['staged_count'],2)
        self.assertTrue(all(x['authority']=='RESEARCH_PROPOSAL_ONLY'
                            for x in result['staged_research_candidates']))

    def test_repeated_observation_idempotent(self):
        a=tick(deferred=[{'mission_id':'cache_fill_ttl',
                           'reason':'SOURCE_PIN_DRIFT_REVIEW_REQUIRED'}])
        b=tick(deferred=[{'mission_id':'cache_fill_ttl',
                           'reason':'SOURCE_PIN_DRIFT_REVIEW_REQUIRED'}])
        self.assertEqual(a,b)

    def test_limited_to_three_suggestions(self):
        m=manifest(missions=[
            mission('cache_fill_ttl'),mission('forge_read_budget'),
            mission('skill_journal_budget'),mission('fourth_issue')])
        problems=[{'mission_id':x['mission_id'],
                   'reason':'SOURCE_PIN_DRIFT_REVIEW_REQUIRED'} for x in m['missions']]
        self.assertEqual(tick(m=m,deferred=problems)['staged_count'],3)

    def test_active_jobs_do_not_report_idle(self):
        state={'a': {'status':'running'},'b': {'status':'pending'}}
        result=tick(state=state)
        self.assertEqual(result['state'],'EXECUTION_OR_ADMISSION_IN_PROGRESS')



class NativeReflexLeaseHandoffTests(unittest.TestCase):
    """No host actions: a second fd models the director's required SH lease."""

    @classmethod
    def setUpClass(cls):
        entry = Path(__file__).with_name('owner_native_reflex_successor_entry.py')
        spec = importlib.util.spec_from_file_location('nox_reflex_lockfix', entry)
        cls.entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.entry)

    def test_boot_releases_ex_before_director_acquires_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'owner_maintenance.lock'
            lock.write_bytes(b'')
            fd = os.open(lock, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                class FakeDirector:
                    def start_checked(self, root, require_native_status):
                        self_root = root
                        self.assert_native = require_native_status
                        shared = os.open(lock, os.O_RDONLY)
                        try:
                            fcntl.flock(shared, fcntl.LOCK_SH | fcntl.LOCK_NB)
                            return {'pid': 999, 'start_ticks': 42}
                        finally:
                            os.close(shared)

                director = FakeDirector()
                result = self.entry._start_after_lease_release(fd, director)
                self.assertEqual(result['pid'], 999)
                self.assertTrue(director.assert_native)
            finally:
                os.close(fd)

    def test_failed_boot_leaves_no_ex_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'owner_maintenance.lock'
            lock.write_bytes(b'')
            fd = os.open(lock, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                class BrokenDirector:
                    def start_checked(self, root, require_native_status):
                        raise RuntimeError('simulated BACKOFF')

                with self.assertRaisesRegex(RuntimeError, 'BACKOFF'):
                    self.entry._start_after_lease_release(fd, BrokenDirector())
                shared = os.open(lock, os.O_RDONLY)
                try:
                    fcntl.flock(shared, fcntl.LOCK_SH | fcntl.LOCK_NB)
                finally:
                    os.close(shared)
            finally:
                os.close(fd)

    def test_backoff_recovery_requires_absent_pid(self):
        check = self.entry._supervisor_is_quiescent
        for state in ('STOPPED', 'BACKOFF', 'FATAL', 'EXITED'):
            self.assertTrue(check({'state': state, 'pid': None}))
        for state in ('RUNNING', 'STARTING', 'STOPPING', 'UNKNOWN'):
            self.assertFalse(check({'state': state, 'pid': None}))
        self.assertFalse(check({'state': 'BACKOFF', 'pid': 678}))
        self.assertFalse(check(None))

    def test_backoff_is_settled_before_restoring_original(self):
        class SupervisorStub:
            state = 'BACKOFF'
            calls = 0
            def supervisor(self, command):
                assert command == 'status'
                return {'state': self.state, 'pid': None}
            def stop_checked(self):
                self.calls += 1
                self.state = 'STOPPED'
        stub = SupervisorStub()
        self.entry._settle_supervisor_before_restore(stub)
        self.assertEqual(stub.calls, 1)
        self.assertEqual(stub.state, 'STOPPED')

    def test_rollback_rejects_unsettled_supervisor(self):
        class SupervisorStub:
            def supervisor(self, command):
                return {'state': 'RUNNING', 'pid': 555}
            def stop_checked(self):
                raise AssertionError('must not stop foreign live director')
        with self.assertRaisesRegex(RuntimeError, 'RESTORE_DIRECTOR_NOT_QUIESCENT'):
            self.entry._settle_supervisor_before_restore(SupervisorStub())

    def test_upgrade_and_rollback_both_use_unlocked_start(self):
        body = inspect.getsource(self.entry.run)
        self.assertIn('started = _start_after_lease_release(fd, h)', body)
        self.assertIn("receipt['restored_director'] = _start_after_lease_release(fd, h)", body)
        self.assertIn("require(_supervisor_is_quiescent(present), 'UNKNOWN_DIRECTOR_NO_ROLLBACK')", body)
        self.assertIn('_settle_supervisor_before_restore(h)', body)


if __name__ == '__main__':
    unittest.main()
