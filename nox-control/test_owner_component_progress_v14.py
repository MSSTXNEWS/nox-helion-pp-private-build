#!/usr/bin/env python3
"""V14 B6: original dispatcher progress is never inferred from PID alone."""
import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name('owner_component_tasks.py')
spec=importlib.util.spec_from_file_location('nox_owner_component_v14',SOURCE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def claim(current=7, *, nonce='a'*24, pid=4711, ticks=321, metric='completed_items'):
    return {'nonce':nonce,'pid':pid,'start_ticks':ticks,'metric':metric,
            'current':current,'source_receipt_sha256':'a'*64}


class ProgressEvidenceTests(unittest.TestCase):
    def test_pid_only_and_first_sample_do_not_pass(self):
        self.assertEqual(mod._compare_progress(None,{'tasks':{'x':claim()}},200)['state'],
                         'HOLD_NO_COMPARABLE_PRIOR_SAMPLE')
        old={'observed_at':100,'tasks':{'x':{**claim(), 'current':None}}}
        self.assertEqual(mod._compare_progress(old,{'tasks':{'x':claim()}},200)['advancing'],0)

    def test_true_local_delta_is_unattested(self):
        old={'observed_at':100,'tasks':{'x':claim(5)}}
        new={'tasks':{'x':claim(6)}}
        v=mod._compare_progress(old,new,201)
        self.assertEqual(v['state'],'OBSERVED_LOCAL_COUNTER_ADVANCE_UNATTESTED')
        self.assertEqual(v['advancing'],1)
        self.assertNotIn('native_verified',v)

    def test_same_pid_reused_with_different_startticks_not_progress(self):
        old={'observed_at':100,'tasks':{'x':claim(5,ticks=111)}}
        new={'tasks':{'x':claim(6,ticks=222)}}
        v=mod._compare_progress(old,new,201)
        self.assertEqual(v['advancing'],0)
        self.assertEqual(v['new_claim_or_process'],1)

    def test_nonce_change_not_progress(self):
        old={'observed_at':100,'tasks':{'x':claim(5)}}
        new={'tasks':{'x':claim(6,nonce='b'*24)}}
        self.assertEqual(mod._compare_progress(old,new,201)['advancing'],0)

    def test_stale_counter_requires_time_and_never_restart(self):
        old={'observed_at':100,'tasks':{'x':claim(5)}}
        new={'tasks':{'x':claim(5)}}
        self.assertEqual(mod._compare_progress(old,new,120)['possible_stalled'],0)
        v=mod._compare_progress(old,new,300)
        self.assertEqual(v['state'],'POSSIBLE_STALL_NO_RESTART_AUTHORITY')
        self.assertEqual(v['possible_stalled'],1)

    def test_boolean_and_regressed_counter_no_false_positive(self):
        old={'observed_at':100,'tasks':{'x':claim(8)}}
        self.assertEqual(mod._compare_progress(old,{'tasks':{'x':claim(True)}},300)['advancing'],0)
        self.assertEqual(mod._compare_progress(old,{'tasks':{'x':claim(7)}},300)['advancing'],0)

    def test_bounded_strict_json_rejects_duplicates_nonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'
            for payload in ('{"tasks":{},"tasks":{}}','{"foo":NaN}', '{"a":Infinity}'):
                p.write_text(payload)
                with self.assertRaises(ValueError):mod._strict_progress_json(p)
            p.write_bytes(b'{' + b'x'*(1024*1024) + b'}')
            with self.assertRaises(ValueError):mod._strict_progress_json(p)
            p.unlink();p.symlink_to(Path(d)/'secret')
            with self.assertRaises((OSError,ValueError)):mod._strict_progress_json(p)

    def test_snapshot_requires_real_claim_pid_and_counter_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            proc=root/'proc/4711';proc.mkdir(parents=True)
            (proc/'stat').write_text('4711 (nox dispatcher) S '+' '.join(['0']*18+['321']+['0']*6))
            row={'status':'running','owner_claim':{'pid':4711,'nonce':'a'*24},
                 'progress':{'metric':'completed_items','current':7,'source_receipt_sha256':'a'*64}}
            snap=mod._progress_snapshot({'tasks':{'x':row}},root/'proc',100)
            self.assertEqual(snap['tasks']['x']['start_ticks'],321)
            self.assertEqual(snap['tasks']['x']['current'],7)
            row['progress']['current']=True
            snap=mod._progress_snapshot({'tasks':{'x':row}},root/'proc',101)
            self.assertIsNone(snap['tasks']['x']['current'])
            row['progress']['current']=7;row['owner_claim']['pid']=4712
            snap=mod._progress_snapshot({'tasks':{'x':row}},root/'proc',102)
            self.assertEqual(snap['tasks'],{})

    def test_existing_owner_stop_never_allows_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'state').mkdir()
            (root/'STOP').write_text('OWNER')
            observation=mod._dispatcher_progress_observation(root,root/'proc',1000)
            self.assertEqual(observation['state'],'HOLD_OWNER_STOP_PRESERVE')
            self.assertFalse(observation['restart_authorized'])
            self.assertFalse(observation['live_progress_verified'])
            self.assertTrue((root/'STOP').exists())

    def test_real_readback_previous_snapshot_progress_but_no_verified_native(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);proc=root/'proc/4711';proc.mkdir(parents=True)
            (proc/'stat').write_text('4711 (worker) S '+' '.join(['0']*18+['321']+['0']*6))
            state=root/'state/dispatcher';state.mkdir(parents=True)
            components=root/'state/owner_components';components.mkdir()
            row={'status':'running','owner_claim':{'pid':4711,'nonce':'a'*24},
                 'progress':{'metric':'optimizer_steps','current':9,'source_receipt_sha256':'a'*64}}
            (state/'state.json').write_text(json.dumps({'tasks':{'x':row}}))
            prior={'schema':'NOX_OWNER_COMPONENT_V1',
                   'evidence':{'progress_observation':{'snapshot':{
                       'observed_at':100,'tasks':{'x':claim(8,metric='optimizer_steps')}}}}}
            (components/'owner.dispatcher.json').write_text(json.dumps(prior))
            v=mod._dispatcher_progress_observation(root,root/'proc',200)
            self.assertEqual(v['state'],'OBSERVED_LOCAL_COUNTER_ADVANCE_UNATTESTED')
            self.assertFalse(v['live_progress_verified'])
            self.assertEqual(v['writer_lease'],'UNKNOWN_NOT_OBTAINED')

    def test_v14_six_configured_never_means_six_native_workers(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'config').mkdir()
            (root/'scripts').mkdir()
            (root/'scripts/nox_dispatcher_t855u.py').write_text('running = True\n')
            with mock.patch.object(mod,'ROOT',root), mock.patch.object(
                mod,'_dispatcher_progress_observation',
                return_value={'state':'OBSERVED_LOCAL_COUNTER_ADVANCE_UNATTESTED',
                              'live_progress_verified':False, 'writer_lease':'UNKNOWN_NOT_OBTAINED'}):
                for raw,valid_config in ((6,True),('6',False),(True,False),(-1,False),(6.0,False)):
                    (root/'config/dispatcher_agents_t868u.json').write_text(
                        json.dumps({'workers':raw,'min_workers':3,'max_workers':6}))
                    evidence=mod.dispatcher()
                    self.assertIs(evidence['configuration_verified'],valid_config)
                    self.assertIs(evidence['verified'],False)
                    self.assertIs(evidence['native_worker_count_verified'],False)
                    self.assertIsNone(evidence['native_worker_count'])
                    self.assertIs(evidence['worker_claims_verified'],False)
                    self.assertIn('NATIVE_SIX_WORKER_PID_START_TICKS_TASKID_CLAIMS_REQUIRED',
                                  evidence['blockers'])

    def test_v14_component_receipt_does_not_accept_config_as_native_done(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'config').mkdir()
            (root/'scripts').mkdir()
            (root/'scripts/nox_dispatcher_t855u.py').write_text('running = True\n')
            (root/'config/dispatcher_agents_t868u.json').write_text('{"workers":6}')
            with mock.patch.object(mod,'ROOT',root), mock.patch.object(
                mod,'_dispatcher_progress_observation',
                return_value={'state':'HOLD_NO_COMPARABLE_PRIOR_SAMPLE',
                              'live_progress_verified':False, 'writer_lease':'UNKNOWN_NOT_OBTAINED'}):
                success,output=mod.run_component_task({'id':'owner.dispatcher','claimed_by':'synthetic'})
                self.assertFalse(success)
                self.assertFalse(output['verified'])
                receipt=json.loads((root/'state/owner_components/owner.dispatcher.json').read_text())
                self.assertFalse(receipt['success'])
                self.assertEqual(receipt['evidence']['workers'],6)
                self.assertFalse(receipt['evidence']['native_worker_count_verified'])

if __name__=='__main__':unittest.main()
