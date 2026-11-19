"""Real local confinement/CAS QA; it does not assert native deployment."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest

import owner_project_executor as executor
from owner_subagent_processes import Subagents


HERE = Path(__file__).parent
BASE = b'def value():\n    return 1\n'
FIXED = b'def value():\n    return 2\n'
TEST = b'''import unittest
import source
class SourceTest(unittest.TestCase):
    def test_actual_change(self):
        self.assertEqual(source.value(), 2)
'''


def config_for(path):
    root = path / 'source'
    root.mkdir()
    package, state = path / 'package', path / 'state'
    package.mkdir()
    state.mkdir()
    python = Path('/usr/bin/python3').resolve()
    bwrap = Path(shutil.which('bwrap')).resolve()
    return {'schema':executor.CONFIG_SCHEMA, 'enabled':True, 'max_workers':3,
            'package_root':str(package), 'state_root':str(state),
            'roots':{'TEST_SOURCE':{'path':str(root), 'integration_kind':'SOURCE_WORKSPACE',
                                  'allowed_paths':['source.py', 'test_source.py', 'extra.py'], 'deny_paths':[]}},
            'sandbox':{'backend':'bwrap_seccomp', 'python':str(python),
                       'python_sha256':executor.digest(python.read_bytes()),
                       'bwrap':str(bwrap), 'bwrap_sha256':executor.digest(bwrap.read_bytes()),
                       'uid':65534, 'gid':65534, 'memory_mb':128},
            'source_pins':{name:executor.digest((HERE / name).read_bytes()) for name in executor.SOURCE_FILES}}


def plan_for(config, *, number=0, target=FIXED, test=TEST):
    root = Path(config['roots']['TEST_SOURCE']['path'])
    (root / 'source.py').write_bytes(BASE)
    (root / 'test_source.py').write_bytes(test)
    sha = executor.digest(target)
    plan = {'schema':executor.SCHEMA, 'task_id':'I-48.project.' + str(number),
            'parent_task_id':'I-48', 'queue_id':executor.QUEUE_IDS[number % 4],
            'root_id':'TEST_SOURCE', 'operation':'apply_reviewed_files',
            'review_origin':'OWNER_REVIEWED', 'context':[
                {'path':'source.py', 'sha256':executor.digest(BASE)},
                {'path':'test_source.py', 'sha256':executor.digest(test)}],
            'files':[{'path':'source.py', 'before_sha256':executor.digest(BASE),
                      'after_sha256':sha, 'payload_sha256':sha}],
            'verification':{'kind':'python_unittest', 'modules':['test_source'],
                            'min_tests':1, 'timeout_sec':15},
            'acceptance_scope':'SOURCE_PATCH_TESTED', 'original_task_accepted':False}
    return plan, {sha:target}


class ProjectExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = config_for(self.path)

    def prepare(self, plan=None, blobs=None, claim='a' * 24):
        if plan is None:
            plan, blobs = plan_for(self.config)
        ref = executor.materialize_plan(plan, blobs, self.config)
        result = executor.prepare(ref, self.config, claim)
        return plan, ref, result

    def test_real_isolated_tests_then_parent_integrates(self):
        plan, ref, result = self.prepare()
        self.assertEqual(result['state'], 'PREPARED', result)
        self.assertTrue(result['sandbox_verified'])
        self.assertTrue(result['trusted_tests_unchanged'])
        root = Path(self.config['roots']['TEST_SOURCE']['path'])
        self.assertEqual((root / 'source.py').read_bytes(), BASE)
        committed = executor.integrate_prepared(ref, self.config, 'a' * 24, gate=lambda:True)
        self.assertEqual(committed['state'], 'INTEGRATED')
        self.assertEqual((root / 'source.py').read_bytes(), FIXED)
        self.assertFalse(committed['original_task_accepted'])
        repeated = executor.integrate_prepared(ref, self.config, 'a' * 24, gate=lambda:True)
        self.assertEqual(repeated, committed)

    def test_failed_test_never_changes_shared_source(self):
        plan, blobs = plan_for(self.config, target=b'def value():\n    return 9\n')
        _, ref, result = self.prepare(plan, blobs)
        self.assertEqual(result['state'], 'FAILED_TESTS', result)
        self.assertTrue(result['sandbox_verified'])
        self.assertEqual(result['project_evidence']['tests']['failures'], 1)
        with self.assertRaisesRegex(executor.ProjectHold, 'NOT_PREPARED'):
            executor.integrate_prepared(ref, self.config, 'a' * 24, gate=lambda:True)
        self.assertEqual((Path(self.config['roots']['TEST_SOURCE']['path']) / 'source.py').read_bytes(), BASE)

    def test_import_failure_reports_the_missing_dependency(self):
        plan, blobs = plan_for(self.config, test=b'import nox_missing_fixture_dependency\n')
        _, _, result = self.prepare(plan, blobs)
        self.assertEqual(result['state'], 'BLOCKED_SANDBOX')
        self.assertIn('ModuleNotFoundError', result['project_evidence']['reason'])
        self.assertIn('nox_missing_fixture_dependency', result['project_evidence']['reason'])
        self.assertFalse(result['passed'])

    def test_model_test_fix_test_uses_distinct_plan_journals(self):
        failed, blobs = plan_for(self.config, target=b'def value():\n    return 3\n')
        _, _, result = self.prepare(failed, blobs)
        self.assertEqual(result['state'], 'FAILED_TESTS', result)
        fixed = copy.deepcopy(failed)
        fixed['files'][0].update(after_sha256=executor.digest(FIXED), payload_sha256=executor.digest(FIXED))
        _, _, result = self.prepare(fixed, {executor.digest(FIXED):FIXED})
        self.assertEqual(result['state'], 'PREPARED', result)
        journals = list(Path(self.config['state_root']).glob('attempts/*/*/*/journal.json'))
        self.assertEqual(len(journals), 2)

    def test_source_drift_prevents_shared_cas(self):
        _, ref, result = self.prepare()
        self.assertEqual(result['state'], 'PREPARED', result)
        source = Path(self.config['roots']['TEST_SOURCE']['path']) / 'source.py'
        source.write_bytes(b'foreign change\n')
        with self.assertRaisesRegex(executor.ProjectHold, 'SOURCE_CAS_CHANGED'):
            executor.integrate_prepared(ref, self.config, 'a' * 24, gate=lambda:True)
        self.assertEqual(source.read_bytes(), b'foreign change\n')

    def test_stop_during_commit_rolls_back_and_verifies_preimage(self):
        plan, blobs = plan_for(self.config)
        extra = b'extra = 1\n'
        plan['files'].append({'path':'extra.py', 'before_sha256':None,
                             'after_sha256':executor.digest(extra), 'payload_sha256':executor.digest(extra)})
        blobs[executor.digest(extra)] = extra
        _, ref, result = self.prepare(plan, blobs)
        self.assertEqual(result['state'], 'PREPARED', result)
        calls = []
        def gate():
            calls.append(True)
            return len(calls) < 3
        outcome = executor.integrate_prepared(ref, self.config, 'a' * 24, gate=gate)
        self.assertEqual(outcome['state'], 'ROLLED_BACK')
        self.assertTrue(outcome['rollback_verified'])
        root = Path(self.config['roots']['TEST_SOURCE']['path'])
        self.assertEqual((root / 'source.py').read_bytes(), BASE)
        self.assertFalse((root / 'extra.py').exists())

    def test_rollback_never_overwrites_an_external_edit(self):
        _, ref, result = self.prepare()
        self.assertEqual(result['state'], 'PREPARED', result)
        source = Path(self.config['roots']['TEST_SOURCE']['path']) / 'source.py'
        calls = []
        def gate():
            calls.append(True)
            if len(calls) == 3:
                source.write_bytes(b'foreign concurrent edit\n')
                return False
            return True
        outcome = executor.integrate_prepared(ref, self.config, 'a' * 24, gate=gate)
        self.assertEqual(outcome['state'], 'HOLD_RECOVERY_REQUIRED')
        self.assertEqual(source.read_bytes(), b'foreign concurrent edit\n')

    def test_model_cannot_modify_trusted_tests(self):
        plan, blobs = plan_for(self.config)
        contract = {'schema':executor.CONTRACT_SCHEMA,
                    **{key:plan[key] for key in ('task_id','parent_task_id','queue_id','root_id',
                                                 'context','verification','acceptance_scope')},
                    'editable_paths':['source.py'], 'allowed_new_paths':[]}
        sha = executor.digest(executor.encoded(contract))
        executor.write_atomic(Path(self.config['package_root']) / 'contracts' / (sha + '.json'),
                              executor.encoded(contract))
        plan.update(review_origin='MODEL_CANDIDATE', contract_sha256=sha)
        executor.materialize_plan(plan, blobs, self.config, approved_contract_sha256=sha)
        replacement = b'import unittest\n'
        plan['files'].append({'path':'test_source.py', 'before_sha256':executor.digest(TEST),
                             'after_sha256':executor.digest(replacement), 'payload_sha256':executor.digest(replacement)})
        blobs[executor.digest(replacement)] = replacement
        with self.assertRaisesRegex(executor.ProjectHold, 'MODEL_EDIT_SCOPE|MODEL_TEST_MUTATION'):
            executor.materialize_plan(plan, blobs, self.config, approved_contract_sha256=sha)

    def test_three_processes_execute_real_source_checks_and_reuse_pid(self):
        # Independent approved roots avoid intentionally racing shared preimages.
        items = []
        for number in range(4):
            folder = self.path / ('slot' + str(number))
            folder.mkdir()
            config = config_for(folder)
            plan, blobs = plan_for(config, number=number)
            ref = executor.materialize_plan(plan, blobs, config)
            items.append({'id':plan['task_id'], 'subagent':('runtime','memory','weights')[number % 3],
                          'task':'Apply the exact source repair and test it', 'depends_on':[],
                          '_native_project_context':{'reference':ref, 'config':config, 'claim':'b' * 24}})
        with Subagents(['runtime','memory','weights'], timeout=30) as pool:
            initial = {role:child.pid for role, child in pool.processes.items()}
            for item in items[:3]:
                pool.submit(item)
            results = []
            deadline = time.monotonic() + 40
            while len(results) < 3 and time.monotonic() < deadline:
                result = pool.poll(.1)
                if result:
                    results.append(result)
            self.assertEqual(len(results), 3)
            for result in results:
                self.assertEqual(result['state'], 'PREPARED', result)
                self.assertTrue(result['sandbox_verified'])
                self.assertEqual(result['pid'], initial[result['role']])
            pool.submit(items[3])
            result = None
            while result is None and time.monotonic() < deadline:
                result = pool.poll(.1)
            self.assertIsNotNone(result)
            self.assertEqual(result['state'], 'PREPARED', result)
            self.assertEqual(result['pid'], initial['runtime'])


if __name__ == '__main__':
    unittest.main()
