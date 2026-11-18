"""Integration test with a deterministic model stub and real confined verifier.

This proves the planner/executor boundary, not successful native model inference.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import owner_project_executor as executor
import owner_project_model_bridge as bridge
import owner_project_planner as planner
from test_owner_project_executor import config_for, BASE, FIXED, TEST


class BridgeIntegrationTest(unittest.TestCase):
    def test_failed_candidate_corrected_tested_and_parent_integrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = config_for(Path(tmp))
            root = Path(config['roots']['TEST_SOURCE']['path'])
            (root/'source.py').write_bytes(BASE)
            (root/'test_source.py').write_bytes(TEST)
            contract = {'schema': planner.SCHEMA, 'task_id':'1A03.bridge_proof',
                'parent_task_id':'1A03', 'queue_id':'Q1_RUNTIME_CHAT', 'root_id':'TEST_SOURCE',
                'instruction':'Return 2 from value.', 'context':[
                    {'path':'source.py','sha256':planner.sha(BASE)},
                    {'path':'test_source.py','sha256':planner.sha(TEST)}],
                'editable_paths':['source.py'], 'allowed_new_paths':[],
                'verification':{'kind':'python_unittest','modules':['test_source'],
                                'min_tests':1,'timeout_sec':15},
                'acceptance_scope':'SOURCE_PATCH_TESTED'}
            raw = planner.canonical(contract); sha = planner.sha(raw)
            contracts = Path(config['package_root'])/'contracts'
            contracts.mkdir(); (contracts/(sha+'.json')).write_bytes(raw)
            config['model'] = {'expected_model_id':'unit-model-stub', 'max_tokens':900,
                'lock_path':str(Path(tmp)/'model.lock'),
                'source_pins':{name:planner.sha((Path(bridge.__file__).parent/name).read_bytes())
                               for name in bridge.SOURCE_FILES}}
            wrong = b'def value():\n    return 3\n'
            def patch(before, old, new):
                return {'action':'patch','changes':[{'path':'source.py',
                    'before_sha256':planner.sha(before),'edits':[{'old':old,'new':new}]}]}
            actions = [patch(BASE,'return 1','return 3'), {'action':'test'},
                patch(wrong,'return 3','return 2'), {'action':'test'}, {'action':'finish'}]
            calls = []
            def model(messages):
                calls.append(json.loads(json.dumps(messages)))
                return json.dumps(actions[len(calls)-1])
            item = {'id':contract['task_id'], '_native_project_context':{
                'reference':{'contract_sha256':sha}, 'config':config, 'claim':'b'*24}}
            with mock.patch.object(bridge, 'LocalModelClient', return_value=model):
                result = bridge.execute(item)
            self.assertEqual(result['state'], 'PREPARED', result)
            self.assertEqual(result['planner_receipt']['model_turns'], 5)
            self.assertEqual((root/'source.py').read_bytes(), BASE)
            self.assertIn('AssertionError', calls[2][-1]['content'])
            final = executor.integrate_prepared(result['reference'], config,
                result['prepared_claim'], gate=lambda:True)
            self.assertEqual(final['state'], 'INTEGRATED')
            self.assertEqual((root/'source.py').read_bytes(), FIXED)
            self.assertFalse(final['original_task_accepted'])
            self.assertEqual(len(list(Path(config['state_root']).glob('attempts/*/*/*/journal.json'))), 2)


if __name__ == '__main__':
    unittest.main()
