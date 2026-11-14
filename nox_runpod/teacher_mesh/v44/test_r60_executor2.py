import unittest
from r60_executor2 import prepared_tasks,merge_without_overwrite

class TestR60(unittest.TestCase):
    def test_exactly_thirty_unique_owner_ids(self):
        tasks=prepared_tasks();ids=[x['task_id'] for x in tasks]
        self.assertEqual(len(ids),30)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(ids, [f'R60-{i:03d}' for i in list(range(21,41))+list(range(51,61))])
        self.assertTrue(all(x['job_id'] is None and not x['production_verified'] for x in tasks))
    def test_merge_preserves_existing_verified_receipts(self):
        old={'task_id':'R60-021','status':'DONE','job_id':'native:927','native_receipt_sha256':'a'*64}
        r=merge_without_overwrite({'tasks':[old]})
        self.assertEqual(r['task_count'],30)
        self.assertEqual(r['tasks'][0],old)
        self.assertNotIn('R60-021',r['missing_executor2_ids'])
        self.assertFalse(r['write_performed'])
        self.assertFalse(r['all_60_present'])
    def test_no_master_not_claimed(self):
        self.assertEqual(merge_without_overwrite({})['state'],'HOLD_MASTER_MISSING')
    def test_duplicate_fails(self):
        self.assertEqual(merge_without_overwrite({'tasks':[{'task_id':'R60-021'},{'task_id':'R60-021'}]})['state'],'HOLD_DUPLICATE_MASTER_IDS')
    def test_sixty_only_if_all_present(self):
        old=[{'task_id':f'R60-{n:03d}','status':'PENDING'} for n in list(range(1,21))+list(range(41,51))]
        r=merge_without_overwrite({'tasks':old})
        self.assertEqual(r['task_count'],60)
        self.assertTrue(r['all_60_present'])
        self.assertFalse(r['write_performed'])

if __name__=='__main__':unittest.main()
