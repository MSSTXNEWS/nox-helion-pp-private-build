"""Off-server one-shot taskpack and owner-bundle review.

No SSH, native queue writes, restarts, content mutation or claim of runtime PASS.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE/'runtime'))
import owner_systemic_refill as refill


def imported(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ENTRY=imported(HERE/'owner_zip_bounded_refill_entry.py','zip_bounded_entry')
OPERATOR=imported(ROOT/'owner_native_operator.py','zip_owner_transport')
MANIFEST=HERE/'mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json'


class OneShotRefillTests(unittest.TestCase):
    def test_mission_is_a_reviewed_bounded_source_task(self):
        earlier=json.loads(MANIFEST.read_bytes())
        new=deepcopy(earlier)
        new['revision']=3
        new['previous_manifest_sha256']=ENTRY.PREVIOUS
        new['missions']=[ENTRY.mission()]
        new['producer_evidence']={'scope':'synthetic_source_gate_only'}
        refill.validate_manifest(new)
        m=new['missions'][0]
        self.assertEqual(len(m['context']),2)
        self.assertEqual(m['parent_task_id'],'0V14-14')
        self.assertEqual(m['queue_id'],new['registry']['parents']['0V14-14']['queue_id'])
        self.assertEqual(m['context'][0]['sha256'],ENTRY.FILE_SHA)
        self.assertEqual(m['context'][1]['sha256'],ENTRY.TEST_SHA)
        self.assertEqual(m['allowed_new_paths'],[])
        self.assertEqual(m['editable_paths'],['merge_web_source.py'])
        self.assertEqual(m['verification']['min_tests'],6)
        self.assertEqual(m['budget']['max_searches'],0)
        id='0V14-14.relay.zip_extract_budget.'+refill._input(m)[:16]
        contract=refill._contract(m,id)
        self.assertEqual(contract['original_task_accepted'],False)
        self.assertEqual(contract['editable_paths'],['merge_web_source.py'])

    def test_only_existing_owner_manifest_cas_and_helper_are_bundled(self):
        self.assertEqual(
            OPERATOR.FILES['repair'],
            'nox-control/systemic_relay_20261118/owner_zip_bounded_refill_entry.py')
        self.assertEqual(
            OPERATOR.SCOPED_REPAIR_BUNDLES[OPERATOR.FILES['repair']],
            ('owner_systemic_relay_publish.py','continuous_transaction_helpers.py'))
        self.assertEqual(
            {p.name for p in map(Path,OPERATOR.repair_bundle_paths(
                'repair',OPERATOR.FILES['repair'],()))},
            {'owner_systemic_relay_publish.py','continuous_transaction_helpers.py'})
        helper=ROOT/'continuous_executor_20261118/assets/continuous_transaction_helpers.py'
        self.assertEqual(hashlib.sha256(helper.read_bytes()).hexdigest(),ENTRY.HELPER_SHA)

    def test_exact_pinned_source_matches_reviewed_repo_file(self):
        source=HERE/'next_reviewed_source/merge_web_source.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),ENTRY.FILE_SHA)
        self.assertIn('z.extractall(out)',source.read_text(encoding='utf8'))

    def test_no_replay_or_unauthorised_native_cap(self):
        self.assertEqual(ENTRY.PREVIOUS_CONFIG,
          '7c05bfc72caf25fe3e0cd910039b6f4eac846d3f19d7a7a7ceb814bd879c01a5')
        self.assertEqual(ENTRY.PREVIOUS,
          'd58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212')
        self.assertTrue(ENTRY.mission()['repeat_policy']=='ONCE_PER_REVIEWED_REVISION')
        src=(HERE/'owner_zip_bounded_refill_entry.py').read_text(encoding='utf-8')
        for forbidden in ('subprocess.run(', 'os.system(', 'killall ', 'drop_caches', 'supervisorctl restart'):
            self.assertNotIn(forbidden,src)


if __name__=='__main__':
    unittest.main()
