"""Local transactional gates for the reviewed native continuation installer.

Uses the frozen helper's real filesystem writes in temporary directories.
It does not contact a model, supervisor, provider, S03, or the live server.
"""
import copy
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import owner_continuous_executor_install as install


HERE = Path(__file__).resolve().parent
HELPER = HERE/'complete_executor_proc_identity_20261118/reviewed/owner_kernel_self_fd_install.py'
loader = importlib.util.spec_from_file_location('_continuous_frozen_helper_tests', HELPER)
frozen = importlib.util.module_from_spec(loader)
loader.loader.exec_module(frozen)


def fixture():
    runtime = {'scripts/'+name:('new reviewed '+name).encode()
               for name in install.MODULES | install.EXTRA_TOOLS}
    old = {
        'schema':'NOX_NATIVE_SUBAGENT_BINDING_V1', 'instance_id':60509551,
        'owner_authorized':True, 'execution_mode':'NATIVE_PROJECT_V1',
        'mode':'NORMAL', 'target':3, 'global_worker_cap':3,
        'module_pins':{name:install.digest(('old '+name).encode()) for name in install.MODULES},
        'historical_project_source_sha256':['1'*64],
        'historical_leaf_source_sha256':['2'*64],
        'project_executor':{
            'model':{'source_pins':{'owner_project_planner.py':'3'*64,
                                  'owner_project_model_client.py':'4'*64},
                     'temperature':0, 'endpoint':'http://127.0.0.1:8098/v1/chat/completions'},
            'roots':{'NOX_PROJECT_SOURCE':{'path':str(install.ROOT/install.SOURCE),
                        'integration_kind':'SOURCE_WORKSPACE',
                        'allowed_paths':['source.py','test_existing.py'], 'deny_paths':[]}},
            'sandbox':{'network_denied':True,'memory_mb':256}},
        'catalog':{'schema':'NOX_AUTONOMY_PROCESS_POOL_V1', 'tasks':[
            {'id':'old.task','handler':'owner_native_project_work',
             'params':{'parent_task_id':'old','plan_sha256':'5'*64}, 'deps':[]}]},
        'policy':{'sha256':'6'*64},
        'unrelated':{'chat_priority':True,'S03_required':True,
                     'original_history':{'old.task':{'claim':'claim-1','result':'receipt-1'}}}}
    old['catalog_sha256'] = install.digest(install.encoded(old['catalog']))
    additions = {'test_nox_continuation_'+str(n)+'.py':('trusted test '+str(n)).encode()
                 for n in range(3)}
    contracts, rows = {}, []
    for n in range(3):
        parent = 'P'+str(n)
        contract = {'schema':'NOX_PROJECT_PLANNER_CONTRACT_V1',
            'task_id':parent+'.continuation', 'parent_task_id':parent,
            'root_id':'NOX_PROJECT_SOURCE', 'acceptance_scope':'SOURCE_PATCH_TESTED',
            'original_task_accepted':False, 'queue_id':'Q'+str(n+1)}
        pin = install.digest(install.encoded(contract))
        contracts[pin] = contract
        rows.append({'id':contract['task_id'],'handler':'owner_native_project_work',
            'resource':'CPU_LIGHT','deps':[], 'queue_id':contract['queue_id'],
            'source_sha256':install.digest(runtime['scripts/owner_subagent_dispatcher.py']),
            'params':{'parent_task_id':parent,'contract_sha256':pin}})
    return old, runtime, additions, contracts, rows


class TransactionTests(unittest.TestCase):
    def test_partial_apply_restores_original_config_and_removes_only_new_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = install.SOURCE+'/test_nox_first.py'
            second = install.SOURCE+'/test_nox_second.py'
            existing = install.SOURCE+'/keep.py'
            frozen.atomic(root/install.CONFIG, b'old config')
            frozen.atomic(root/existing, b'existing source')
            changes = {install.CONFIG:b'new config', first:b'first test', second:b'second test'}
            before = {install.CONFIG:b'old config', first:None, second:None}
            applied = []
            def fail_after_first(path, raw, mode=0o600):
                if path == root/second:
                    raise OSError('local injected failure after first additive test')
                frozen.atomic(path, raw, mode)
            helper = SimpleNamespace(read_regular=frozen.read_regular, atomic=fail_after_first,
                                     rollback_transaction=frozen.rollback_transaction)
            with self.assertRaises(OSError):
                install.apply_tracked(root, changes, before, helper, applied)
            self.assertEqual(applied, list(changes))
            self.assertEqual((root/first).read_bytes(), b'first test')
            outcomes = install.rollback_owned(root, changes, before, helper, applied)
            self.assertEqual((root/install.CONFIG).read_bytes(), b'old config')
            self.assertEqual((root/existing).read_bytes(), b'existing source')
            self.assertFalse((root/first).exists())
            self.assertFalse((root/second).exists())
            self.assertEqual(outcomes[first], 'OWN_NEW_TEST_REMOVED_AFTER_ROLLBACK')
            self.assertEqual(outcomes[second], 'NEW_TEST_ABSENT')

    def test_rollback_preserves_foreign_additive_bytes_and_restores_owned_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            added = install.SOURCE+'/test_nox_first.py'
            frozen.atomic(root/install.CONFIG, b'old config')
            before = {install.CONFIG:b'old config', added:None}
            changes = {install.CONFIG:b'new config', added:b'owned test'}
            applied = []
            install.apply_tracked(root, changes, before, frozen, applied)
            frozen.atomic(root/added, b'foreign newer work')
            with self.assertRaisesRegex(install.Hold, 'NEW_TEST_CHANGED_NO_CLEANUP'):
                install.rollback_owned(root, changes, before, frozen, applied)
            self.assertEqual((root/added).read_bytes(), b'foreign newer work')
            self.assertEqual((root/install.CONFIG).read_bytes(), b'old config')

    def test_concurrent_preimage_change_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen.atomic(root/install.CONFIG, b'foreign config')
            applied = []
            with self.assertRaisesRegex(install.Hold, 'CONCURRENT_WRITE'):
                install.apply_tracked(root, {install.CONFIG:b'new config'},
                    {install.CONFIG:b'old config'}, frozen, applied)
            self.assertEqual(applied, [])
            self.assertEqual((root/install.CONFIG).read_bytes(), b'foreign config')

    def test_rollback_never_overwrites_foreign_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen.atomic(root/install.CONFIG, b'old config')
            applied = []
            changes, before = {install.CONFIG:b'new config'}, {install.CONFIG:b'old config'}
            install.apply_tracked(root, changes, before, frozen, applied)
            frozen.atomic(root/install.CONFIG, b'foreign after write')
            outcomes = install.rollback_owned(root, changes, before, frozen, applied)
            self.assertEqual(outcomes[install.CONFIG], 'FOREIGN_CHANGE_PRESERVED')
            self.assertEqual((root/install.CONFIG).read_bytes(), b'foreign after write')


class CompositionTests(unittest.TestCase):
    def test_append_preserves_prior_catalog_history_and_unrelated_configuration(self):
        old, runtime, additions, contracts, rows = fixture()
        baseline = copy.deepcopy(old)
        result = install.compose(old, runtime, additions, contracts, rows)
        self.assertEqual(old, baseline)
        self.assertEqual(result['catalog']['tasks'][:1], baseline['catalog']['tasks'])
        self.assertEqual(result['catalog']['tasks'][1:], rows)
        self.assertEqual(result['unrelated'], baseline['unrelated'])
        self.assertEqual(result['policy'], baseline['policy'])
        self.assertEqual(result['project_executor']['sandbox'], baseline['project_executor']['sandbox'])
        self.assertEqual(result['project_executor']['model']['endpoint'], baseline['project_executor']['model']['endpoint'])
        for key in ('historical_leaf_source_sha256','historical_project_source_sha256'):
            self.assertEqual(set(result[key]), set(baseline[key]) |
                             {baseline['module_pins']['owner_subagent_dispatcher.py']})
        self.assertEqual(result['catalog_sha256'], install.digest(install.encoded(result['catalog'])))
        # Appending cannot grant additional runtime capabilities or paths.
        self.assertEqual(set(result['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths']),
                         {'source.py','test_existing.py'} | set(additions))
        self.assertEqual(result['global_worker_cap'], 3)

    def test_trusted_test_collision_rejected_without_mutating_config(self):
        old, runtime, additions, contracts, rows = fixture()
        old['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'].append(next(iter(additions)))
        baseline = copy.deepcopy(old)
        with self.assertRaisesRegex(install.Hold, 'TEST_ALREADY_ALLOWED'):
            install.compose(old, runtime, additions, contracts, rows)
        self.assertEqual(old, baseline)

    def test_marker_append_keeps_old_pins_refs_and_provenance(self):
        _, _, additions, _, _ = fixture()
        marker = {'schema':'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1',
            'root':str(install.ROOT/install.SOURCE), 'file_pins':{'source.py':'a'*64},
            'source_refs':[{'kind':'ORIGINAL_SOURCE','sha':'b'*40}],
            'manifest_sha256':'c'*64, 'source_file_count':1, 'original_request':'12345'}
        baseline = copy.deepcopy(marker)
        result = install.extend_marker(marker, additions, 'd'*40)
        self.assertEqual(marker, baseline)
        self.assertEqual(result['file_pins']['source.py'], baseline['file_pins']['source.py'])
        self.assertEqual(result['source_refs'][:-1], baseline['source_refs'])
        self.assertEqual(result['source_refs'][-1]['previous_marker_sha256'],
                         install.digest(install.encoded(baseline)))
        self.assertEqual(result['original_request'], baseline['original_request'])
        self.assertEqual(result['source_file_count'], 4)
        with self.assertRaisesRegex(install.Hold, 'BOOTSTRAP_TEST_COLLISION'):
            install.extend_marker(result, additions, 'e'*40)


if __name__ == '__main__':
    unittest.main()
