"""Focused invariants for native NOX self-observation.

No host mutation, GPU/model call, queue replay, user secrets or dispatcher.
Run with: python -m unittest test_owner_reflex_cycle
"""
from __future__ import annotations

import importlib.util
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
    def test_memory_projection_distinguishes_file_cache_and_shmem(self):
        budget = {'current_bytes': 193*1024**3, 'max_bytes':194*1024**3,
                  'file_bytes':188*1024**3, 'shmem_bytes':75*1024**3,
                  'inactive_file_bytes':105*1024**3,
                  'memory_psi_some_avg10':0, 'memory_psi_full_avg10':0}
        decision = {'projected_memory_ratio': .462, 'eligible': True}
        result = refill.memory_governor_projection(
            {'bounded_cpu_budget':budget, 'bounded_cpu_decision':decision})
        self.assertEqual(result['state'], 'CACHE_HEALTHY')
        self.assertTrue(result['native_bounded_cpu_eligible'])
        self.assertEqual(result['shmem_protected_bytes'], 75*1024**3)
        self.assertFalse(result['global_cache_eviction'])

    def test_memory_governor_pressure_and_missing_metadata_hold(self):
        budget = {'current_bytes': 191*1024**3, 'max_bytes':194*1024**3,
                  'file_bytes':150*1024**3, 'shmem_bytes':75*1024**3,
                  'inactive_file_bytes':55*1024**3,
                  'memory_psi_some_avg10':12, 'memory_psi_full_avg10':3}
        decision = {'projected_memory_ratio':.97, 'eligible':False}
        result = refill.memory_governor_projection(
            {'bounded_cpu_budget':budget,'bounded_cpu_decision':decision})
        self.assertEqual(result['state'],'PRESSURE_CRITICAL')
        self.assertFalse(result['native_bounded_cpu_eligible'])
        self.assertFalse(result['auto_reclaim'])
        self.assertEqual(refill.memory_governor_projection({})['state'],
                         'BOUNDED_CPU_ACCOUNTING_NOT_AVAILABLE')

    def test_memory_projection_corrupt_or_contradictory_counters_hold_cleanly(self):
        unit = 1024**3
        baseline = {'current_bytes': 189*unit, 'max_bytes': 194*unit,
                    'file_bytes': 183*unit, 'shmem_bytes': 75*unit,
                    'inactive_file_bytes': 91*unit,
                    'memory_psi_some_avg10': 0, 'memory_psi_full_avg10': 0}
        good = refill.memory_governor_projection({
            'bounded_cpu_budget': baseline,
            'bounded_cpu_decision': {'projected_memory_ratio': .52, 'eligible': True}})
        self.assertEqual(good['state'], 'CACHE_HEALTHY')
        self.assertEqual(good['raw_headroom_bytes'], 5*unit)
        self.assertEqual(good['reclaimable_file_estimate_bytes'], 91*unit)
        self.assertEqual(good['effective_headroom_estimate_bytes'], 96*unit)
        self.assertTrue(good['reclaimable_estimate_is_not_a_guaranteed_allocation'])
        for changes in ({'file_bytes': '183G'}, {'file_bytes': None},
                        {'file_bytes': 191*unit}, {'shmem_bytes': 184*unit},
                        {'inactive_file_bytes': 184*unit},
                        {'current_bytes': 195*unit}, {'memory_psi_some_avg10': 101},
                        {'memory_psi_full_avg10': float('nan')}):
            with self.subTest(changes=changes):
                row = {**baseline, **changes}
                got = refill.memory_governor_projection({
                    'bounded_cpu_budget': row,
                    'bounded_cpu_decision': {'projected_memory_ratio': .52,
                                              'eligible': True}})
                self.assertEqual(got['state'], 'RESOURCE_METADATA_HOLD')
                self.assertFalse(got['auto_reclaim'])

    def test_exhaustion_is_not_fake_job_or_approval(self):
        result = tick()
        self.assertEqual(result['state'], 'REFILL_REQUIRED')
        self.assertEqual(result['new_native_jobs'], 0)
        self.assertFalse(result['automatic_owner_approval'])
        self.assertEqual(result['registry_original_total'],295)
        self.assertEqual(result['unindexed_original_count'],292)
        self.assertEqual(result['staged_count'],0)

    def test_exhausted_catalog_yields_reviewable_originals_not_jobs(self):
        review = manifest()
        for parent_id in review['registry']['parents']:
            review['registry']['parents'][parent_id]['spec_sha256'] = PIN
        a = tick(m=review)
        b = tick(m=review)
        self.assertEqual(a['state'], 'REFILL_REQUIRED')
        self.assertEqual(a['staged_count'], 2)
        self.assertEqual(a['new_native_jobs'], 0)
        self.assertFalse(a['automatic_owner_approval'])
        self.assertEqual(a['staged_research_candidates'], b['staged_research_candidates'])
        for row in a['staged_research_candidates']:
            self.assertEqual(row['hypothesis'], 'INSPECT_UNREPRESENTED_ORIGINAL')
            self.assertEqual(row['spec_sha256'], PIN)
            self.assertEqual(row['authority'], 'RESEARCH_PROPOSAL_ONLY')
            self.assertFalse(row['new_native_job_created'])
            self.assertNotIn('editable_paths', row)
        self.assertEqual(
            {row['parent_task_id'] for row in a['staged_research_candidates']},
            {'4A02', '3B05'})

    def test_no_backlog_research_when_native_claim_active_or_accepted(self):
        review = manifest()
        for parent_id in review['registry']['parents']:
            review['registry']['parents'][parent_id]['spec_sha256'] = PIN
        accepted = {'id': '3B05', 'handler': 'owner_native_project_work',
                    'status': 'done', 'original_task_accepted': True}
        pending = {'id': 'live', 'handler': 'owner_native_project_work',
                   'status': 'running'}
        result = tick(m=review, state={'3B05': accepted, 'live': pending})
        self.assertEqual(result['state'], 'EXECUTION_OR_ADMISSION_IN_PROGRESS')
        self.assertEqual(result['staged_count'], 0)
        self.assertEqual(result['new_native_jobs'], 0)
        exhausted = tick(m=review, state={'3B05': accepted})
        self.assertEqual([x['parent_task_id'] for x in exhausted['staged_research_candidates']],
                         ['4A02'])

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
            'handler':'owner_native_project_work',
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
        state={'a': {'handler':'owner_native_project_work','status':'running'},
               'b': {'handler':'owner_native_typed_leaf','status':'pending'}}
        result=tick(state=state)
        self.assertEqual(result['state'],'EXECUTION_OR_ADMISSION_IN_PROGRESS')


if __name__ == '__main__':
    unittest.main()
