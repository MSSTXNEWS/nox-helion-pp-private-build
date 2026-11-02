"""Executable isolation/ERR25 tests for real FASTLANE-2 code, not Windows EXE QA."""
from __future__ import annotations
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'coordination/e06/fastlane2_accelerator.py'
spec = importlib.util.spec_from_file_location('nox_fastlane2_accelerator', SOURCE)
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)


def command(*args, cwd=None):
    p = subprocess.run(args, cwd=cwd, check=True, capture_output=True, timeout=10)
    return p.stdout.decode().strip()


def task(id, path, *, priority=30, depends=(), status='PENDING', phase='BOOT', lane='A'):
    return {'id': id, 'phase': phase, 'lane': lane, 'priority': priority,
            'paths': [path], 'depends': list(depends), 'status': status,
            'requires_gates': ['G1', 'G2', 'G3', 'G4']}


class FastlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'checkout'
        self.repo.mkdir()
        command('git', 'init', '-q', str(self.repo))
        command('git', 'config', 'user.name', 'Nox Test', cwd=self.repo)
        command('git', 'config', 'user.email', 'nox@example.invalid', cwd=self.repo)
        for p in ('src/first.py', 'src/second.py', 'ui/menu.mjs', 'src/third.py'):
            f = self.repo / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text('READY=True\n', encoding='utf-8')
        command('git', 'add', '.', cwd=self.repo)
        command('git', 'commit', '-qm', 'source', cwd=self.repo)
        self.head = command('git', 'rev-parse', 'HEAD', cwd=self.repo)
        self.ledger = {'schema': 'NOX-FASTLANE2-LEDGER-v1', 'source_head': self.head,
                       'tasks': [task('A1', 'src/first.py', priority=80),
                                 task('A2', 'src/second.py', priority=70),
                                 task('A3', 'src/third.py', priority=20, depends=['A1']),
                                 task('B1', 'ui/menu.mjs', priority=90, lane='B')]}
        self.leases = {'schema': 'NOX-FASTLANE2-LEASES-v1', 'items': []}
        self.gates = {'BOOT': False, 'LOADER': False, 'RELEASE1': False}
        self.snap = a.source_snapshot(self.repo)

    def choose(self, **kwargs):
        return a.choose_free(self.ledger, self.leases, self.snap,
                             phase_acceptance=self.gates, **kwargs)

    def test_01_exact_head_snapshot_verified(self):
        self.assertEqual(self.snap['source_head'], self.head)
        self.assertEqual(self.snap['regular_blobs']['src/first.py'],
                         a.git_blob(b'READY=True\n'))

    def test_02_next_free_skips_busy_owner_without_stealing(self):
        self.leases['items'].append({'task_id':'A1','owner':'M05','run_id':'M05-run-01',
                                      'active':True,'paths':['src/first.py']})
        plan=self.choose(lane='A', preferred='A1')
        self.assertEqual(plan['selected'],'A2')
        self.assertEqual(plan['preferred_blocker'],'LIVE_OWNER_OCCUPIED')
        self.assertEqual(plan['four_gates']['G2'],'NOT_CLAIMED')
        self.assertFalse(plan['autonomous_merge'])

    def test_03_busy_owner_not_released_by_time(self):
        self.leases['items']=[{'task_id':'A1','owner':'M05','run_id':'M05-old-run',
                              'active':True,'paths':['src/first.py']}]
        self.assertEqual(self.choose(preferred='A1')['selected'],'B1')
        self.assertEqual(self.choose(lane='A', preferred='A1')['selected'],'A2')

    def test_04_prior_dependency_not_skipped(self):
        self.assertEqual(next(x for x in self.choose(lane='A')['rejected'] if x['id']=='A3')['reason'],
                         'DEPENDENCY_NOT_INTEGRATED')

    def test_05_dependency_integrated_now_free(self):
        self.ledger['tasks'][0]['status']='INTEGRATED'
        self.assertEqual(self.choose(lane='A', preferred='A3')['selected'],'A3')

    def test_06_boot_only_before_external_phase_evidence(self):
        self.ledger['tasks'].append(task('R1', 'src/third.py', phase='RELEASE1'))
        self.assertEqual(next(x for x in self.choose()['rejected'] if x['id']=='R1')['reason'],
                         'PHASE_GATE_HOLD')
        self.gates['LOADER']=True
        self.assertIn('R1', self.choose()['ready'])

    def test_07_free_evolution_needs_release1_acceptance(self):
        self.ledger['tasks'].append(task('F1','src/third.py',phase='FREE'))
        self.gates['LOADER']=True
        self.assertNotIn('F1',self.choose()['ready'])
        self.gates['RELEASE1']=True
        self.assertIn('F1',self.choose()['ready'])

    def test_08_stop_blocks_all_scheduling(self):
        p=self.choose(stopped=True)
        self.assertEqual(p['state'],'STOPPED')
        self.assertEqual(p['ready'],[])

    def test_09_stale_git_head_denied(self):
        self.ledger['source_head']='f'*40
        with self.assertRaisesRegex(a.FastlaneHold,'STALE_LEDGER_HEAD'):
            self.choose()

    def test_10_dirty_source_denied(self):
        (self.repo/'src/first.py').write_text('DIRTY\n')
        with self.assertRaisesRegex(a.FastlaneHold,'SOURCE_DIRTY_HOLD'):
            a.source_snapshot(self.repo)

    def test_11_dep_cycle_rejected(self):
        self.ledger['tasks'][0]['depends']=['A3']
        with self.assertRaisesRegex(a.FastlaneHold,'DEPENDENCY_CYCLE'):
            self.choose()

    def test_12_bad_path_rejected(self):
        self.ledger['tasks'][1]['paths']=['../other.py']
        with self.assertRaisesRegex(a.FastlaneHold,'TASK_PATH_DEPENDENCY_GATE_INVALID'):
            self.choose()

    def test_13_no_double_task_id(self):
        self.ledger['tasks'].append(dict(self.ledger['tasks'][0]))
        with self.assertRaisesRegex(a.FastlaneHold,'DUPLICATE_TASK_ID'):
            self.choose()

    def test_14_untrusted_lease_path_denied(self):
        self.leases['items']=[{'task_id':'A1','owner':'M01','run_id':'M01-run-01',
                              'active':True,'paths':['ui/menu.mjs']}]
        with self.assertRaisesRegex(a.FastlaneHold,'LEASE_TASK_PATH_MISMATCH'):
            self.choose()

    def test_15_safely_saves_immutable_offtree_candidate_with_readback(self):
        plan=self.choose(preferred='A1', lane='A')
        candidate=self.base/'candidate.py'
        candidate.write_text('READY=True\nENHANCED=True\n')
        out=self.base/'handoff'
        result=a.save_handoff(repo=self.repo,output=out,candidate=candidate,
                             plan=plan,task_id='A1',run_id='M05-run-01')
        data=json.loads(Path(result['receipt_path']).read_text())
        self.assertEqual(data['status'],'OFFTREE_READY_FOR_OWNER_REBASE_NOT_MERGED')
        self.assertEqual(data['candidate_sha256'],result['sha256'])
        self.assertFalse(data['test_execution_by_this_tool'])
        self.assertFalse(data['e07_accepted'])
        self.assertEqual(data['original_git_blob_sha1'],a.git_blob(b'READY=True\n'))
        self.assertEqual((self.repo/'src/first.py').read_text(),'READY=True\n')
        with self.assertRaisesRegex(a.FastlaneHold,'IMMUTABLE_HANDOFF_ALREADY_PRESENT'):
            a.save_handoff(repo=self.repo,output=out,candidate=candidate,
                           plan=plan,task_id='A1',run_id='M05-run-01')

    def test_16_handoff_cannot_target_living_repo(self):
        p=self.choose(preferred='A1',lane='A')
        candidate=self.base/'candidate.py'; candidate.write_text('NEW=True\n')
        with self.assertRaisesRegex(a.FastlaneHold,'OFFTREE_OUTPUT_REQUIRED'):
            a.save_handoff(repo=self.repo,output=self.repo/'work',candidate=candidate,
                           plan=p,task_id='A1',run_id='M05-run-01')

    def test_17_handoff_stale_source_refused(self):
        p=self.choose(preferred='A1',lane='A')
        candidate=self.base/'candidate.py'; candidate.write_text('NEW=True\n')
        (self.repo/'src/first.py').write_text('UPDATED\n')
        command('git','add','.',cwd=self.repo)
        command('git','commit','-qm','advance',cwd=self.repo)
        with self.assertRaisesRegex(a.FastlaneHold,'HANDOFF_SOURCE_PREIMAGE_DRIFT'):
            a.save_handoff(repo=self.repo,output=self.base/'out',candidate=candidate,
                           plan=p,task_id='A1',run_id='M05-run-01')

    def test_18_unsigned_fake_gates_denied(self):
        self.ledger['tasks'][0]['requires_gates']=['G1','G2','G3']
        with self.assertRaisesRegex(a.FastlaneHold,'TASK_PATH_DEPENDENCY_GATE_INVALID'):
            self.choose()

    def test_19_unknown_missing_file_not_scheduled(self):
        self.ledger['tasks'].append(task('A4','src/missing.py',priority=100))
        self.assertEqual(self.choose(lane='A')['selected'],'A1')
        self.assertEqual(next(x for x in self.choose()['rejected'] if x['id']=='A4')['reason'],
                         'SOURCE_PATH_NOT_IN_HEAD')

    def test_20_read_only_plan_no_checkout_write(self):
        before=command('git','status','--porcelain',cwd=self.repo)
        self.choose(lane='A')
        after=command('git','status','--porcelain',cwd=self.repo)
        self.assertEqual(before,after)

    def test_22_reuse_first_finds_existing_equivalent_source(self):
        original = self.repo / 'src' / 'first.py'
        donor = self.repo / 'proposals' / 'first.py'
        donor.parent.mkdir(parents=True)
        donor.write_text('REUSE=True\n')
        command('git','add','.',cwd=self.repo)
        command('git','commit','-qm','add donor',cwd=self.repo)
        self.snap = a.source_snapshot(self.repo)
        self.ledger['source_head'] = self.snap['source_head']
        selected = self.choose(lane='A', preferred='A1')
        self.assertEqual(selected['reuse_before_recoding'][0][0]['path'], 'proposals/first.py')
        self.assertEqual(selected['reuse_before_recoding'][0][0]['status'],
                         'SOURCE_DONOR_CANDIDATE_REVIEW_RIGHTS_AND_SHA256')

    def test_23_reuse_historical_conflicting_donor_not_accepted(self):
        old = self.repo / 'coordination' / 'donor_conflicts' / 'x' / 'first.py'
        old.parent.mkdir(parents=True)
        old.write_text('OLD=True\n')
        command('git','add','.',cwd=self.repo)
        command('git','commit','-qm','old donor',cwd=self.repo)
        self.snap = a.source_snapshot(self.repo)
        self.ledger['source_head'] = self.snap['source_head']
        plan = self.choose(preferred='A1', lane='A')
        self.assertFalse(any(d['path'] == 'coordination/donor_conflicts/x/first.py'
                             for page in plan['reuse_before_recoding'] for d in page))

    def test_24_untrusted_reuse_input_rejected(self):
        with self.assertRaisesRegex(a.FastlaneHold, 'REUSE_LOOKUP_INPUT_INVALID'):
            a.locate_reusable_source(self.snap,'../src/x')

    def test_21_explicit_cli_plan_is_machine_readable_and_no_claim(self):
        lp=self.base/'ledger.json';lp.write_text(json.dumps(self.ledger))
        le=self.base/'leases.json';le.write_text(json.dumps(self.leases))
        ga=self.base/'gates.json';ga.write_text(json.dumps(self.gates))
        buf=io.StringIO()
        with redirect_stdout(buf):
            code=a.main(['plan','--repo',str(self.repo),'--ledger',str(lp),
                         '--leases',str(le),'--acceptance',str(ga),'--lane','A'])
        data=json.loads(buf.getvalue())
        self.assertEqual(code,0)
        self.assertEqual(data['selected'],'A1')
        self.assertFalse(data['release_pass'])


    def test_25_duplicate_json_key_rejected(self):
        path=self.base/'dup.json'
        path.write_text('{"schema":"NOX-FASTLANE2-LEDGER-v1","source_head":"'+self.head+'","tasks":[],"tasks":[]}',encoding='utf-8')
        with self.assertRaisesRegex(a.FastlaneHold,'DUPLICATE_JSON_FIELD'):
            a._read_json(path)

    def test_26_nonfinite_exponent_rejected(self):
        path=self.base/'infinite.json'
        path.write_text('{"x":1e9999}',encoding='utf-8')
        with self.assertRaisesRegex(a.FastlaneHold,'NONFINITE_JSON_NUMBER'):
            a._read_json(path)

    def test_27_identical_candidate_not_promoted(self):
        candidate=self.base/'same.py'
        candidate.write_bytes((self.repo/'src/first.py').read_bytes())
        p=self.choose(lane='A',preferred='A1')
        with self.assertRaisesRegex(a.FastlaneHold,'CANDIDATE_IDENTICAL_TO_SOURCE'):
            a.save_handoff(repo=self.repo,output=self.base/'out',candidate=candidate,
                           plan=p,task_id='A1',run_id='M01-real-run')
        self.assertFalse((self.base/'out').exists())

    def test_28_conflicting_active_path_leases_rejected(self):
        self.ledger['tasks'].append(task('A4','src/first.py'))
        self.leases['items']=[{'task_id':'A1','owner':'M01','run_id':'M01-live', 'active':True,'paths':['src/first.py']},
                              {'task_id':'A4','owner':'M02','run_id':'M02-live', 'active':True,'paths':['src/first.py']}]
        with self.assertRaisesRegex(a.FastlaneHold,'OVERLAPPING_ACTIVE_PATH_LEASE'):
            self.choose(lane='A')

    def test_29_duplicate_active_task_lease_rejected(self):
        self.leases['items']=[{'task_id':'A1','owner':'M01','run_id':'M01-live', 'active':True,'paths':['src/first.py']},
                              {'task_id':'A1','owner':'M01','run_id':'M01-other', 'active':True,'paths':['src/first.py']}]
        with self.assertRaisesRegex(a.FastlaneHold,'OVERLAPPING_ACTIVE_TASK_LEASE'):
            self.choose(lane='A')

    def test_30_1000_task_chain_no_recursion_error(self):
        self.ledger['tasks']=[task(f'A{i:04d}','src/first.py',depends=([f'A{i-1:04d}'] if i else []))
                              for i in range(1000)]
        p=self.choose(lane='A')
        self.assertEqual(p['ready'],['A0000'])

    def test_31_1000_task_cycle_fails_closed(self):
        self.ledger['tasks']=[task(f'A{i:04d}','src/first.py',depends=[f'A{(i+1)%1000:04d}'])
                              for i in range(1000)]
        with self.assertRaisesRegex(a.FastlaneHold,'DEPENDENCY_CYCLE'):
            self.choose(lane='A')

    def test_32_receipt_remains_nonrelease_after_source(self):
        p=self.choose(preferred='A1',lane='A')
        candidate=self.base/'real.py';candidate.write_text('READY=False\n',encoding='utf-8')
        result=a.save_handoff(repo=self.repo,output=self.base/'out',candidate=candidate,
                              plan=p,task_id='A1',run_id='M01-real-run')
        receipt=json.loads(Path(result['receipt_path']).read_text())
        self.assertFalse(receipt['owner_cas_write'])
        self.assertFalse(receipt['e07_accepted'])
        self.assertFalse(receipt['native_model_run'])
        self.assertFalse(receipt['test_execution_by_this_tool'])

    def test_33_duplicate_json_nested_ledger_rejected(self):
        path=self.base/'nested.json'
        path.write_text('{"source_head":"'+self.head+'","schema":"NOX-FASTLANE2-LEDGER-v1","tasks":[{"id":"A1","id":"A2"}]}',encoding='utf-8')
        with self.assertRaisesRegex(a.FastlaneHold,'DUPLICATE_JSON_FIELD'):
            a._read_json(path)

    def test_34_stop_remains_global_even_with_free_task(self):
        p=self.choose(stopped=True,preferred='A1')
        self.assertIsNone(p['selected'])
        self.assertFalse(p['autonomous_merge'])


if __name__=='__main__':
    unittest.main()
