#!/usr/bin/env python3
"""Fixture tests for bounded active queue-row diagnostics."""
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE=Path(__file__).with_name('owner_systemic_relay_observe.py')
SPEC=importlib.util.spec_from_file_location('owner_systemic_relay_observe',SOURCE)
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class ActiveQueueRowReportTests(unittest.TestCase):
    def test_allowlist_hashes_claim_and_never_emits_private_payload(self):
        claim={'pid':42,'worker':'runtime','nonce':'never-print-this'}
        tasks={'task-A':{
            'id':'task-A','handler':'owner_native_project_work','status':'RUNNING',
            'queue_id':'q1','parent_task_id':'parent-A','operation_key':'op-A',
            'owner_claim':claim,'params':{'prompt':'private prompt never print','secret':'secret value'},
            'result':{'receipt':None},
        }}
        report=MODULE.active_queue_row_report(tasks,s03_check=lambda _:{'verified':True})
        rendered=json.dumps(report,sort_keys=True)
        row=report['rows'][0]
        self.assertEqual(report['running_count'],1)
        self.assertEqual(row['task_id'],'task-A')
        self.assertEqual(row['operation_key'],'op-A')
        self.assertEqual(row['claim_sha256'],MODULE.hashlib.sha256(MODULE.encoded(claim)).hexdigest())
        self.assertEqual(row['terminal_receipt_state'],'ABSENT')
        for private in ('never-print-this','private prompt never print','secret value','nonce','params'):
            self.assertNotIn(private,rendered)

    def test_exact_receipt_metadata_and_s03_result_are_projected(self):
        claim={'pid':7,'worker':'memory','nonce':'private'}
        receipt={'schema':'NOX_TEST','phase':'terminal','task_id':'task-B','job_id':'job-B',
                 'queue_id':'qB','claim':claim,'source_sha256':'a'*64,
                 'finished_at':'2026-11-19T00:00:00Z','private_payload':'omit'}
        receipt_sha=MODULE.hashlib.sha256(MODULE.encoded(receipt)).hexdigest()
        seen=[]
        report=MODULE.active_queue_row_report({'task-B':{
            'id':'task-B','handler':'owner_native_typed_leaf','status':'running',
            'owner_claim':claim,'params':{'operation_key':'op-B','prompt':'hidden'},
            'result':{'receipt':receipt,'receipt_sha256':receipt_sha},
        }},s03_check=lambda value:(seen.append(value) or {'verified':True,'s03_item_id':'m2-id'}))
        row=report['rows'][0]
        self.assertEqual(row['operation_key'],'op-B')
        self.assertTrue(row['receipt_sha_matches'])
        self.assertTrue(row['receipt_claim_matches'])
        self.assertEqual(row['s03']['s03_item_id'],'m2-id')
        self.assertEqual(len(seen),1)
        self.assertNotIn('private_payload',json.dumps(row))
        self.assertNotIn('hidden',json.dumps(row))
        self.assertNotIn('private',json.dumps(row))

    def test_row_cap_and_malformed_queue_fail_closed(self):
        tasks={f'task-{n:02}':{'id':f'task-{n:02}','handler':'h','status':'running'}
               for n in range(12)}
        report=MODULE.active_queue_row_report(tasks,row_cap=2)
        self.assertEqual(report['running_count'],12)
        self.assertEqual(len(report['rows']),2)
        self.assertTrue(report['rows_truncated'])
        self.assertEqual(MODULE.active_queue_row_report([],row_cap=2)['reason'],'QUEUE_SHAPE')
        self.assertEqual(MODULE.active_queue_row_report({},row_cap=0)['reason'],'ROW_CAP')

if __name__=='__main__':
    unittest.main()

