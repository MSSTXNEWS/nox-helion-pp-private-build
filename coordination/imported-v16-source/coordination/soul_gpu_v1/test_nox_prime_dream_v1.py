import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from nox_prime_experience_v1 import project
import nox_prime_dream_v1 as d

def turn(root,role,content):
    p=Path(root)/'brain'/'history'/'unified_chat_v1.jsonl'
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'role':role,'content':content,'time':'2026-11-07T14:00:00Z'})+'\n')
class DreamTests(unittest.TestCase):
    def test_real_source_candidate_and_no_s03(self):
        with TemporaryDirectory() as root:
            turn(root,'user','Yesterday we corrected the PowerShell typo')
            turn(root,'assistant','We found a missing quote in source')
            event=project(root)['episodes'][0]['event_id']
            fake={'insights':[{'type':'lesson','title':'Check quoted arguments',
                  'proposed_action':'Review PowerShell syntax in CI',
                  'supporting_event_ids':[event]}]}
            with patch.object(d,'trainer_active',return_value=False),patch.object(d,'_call',return_value=fake):
                r=d.consolidate(root)
            data=json.loads(Path(r['path']).read_text(encoding='utf-8'))
            self.assertEqual(r['insight_count'],1)
            self.assertFalse(data['s03_written'])
            self.assertFalse(data['actions_taken'])
            self.assertEqual(data['insights'][0]['supporting_event_ids'],[event])
            self.assertTrue(data['insights'][0]['requires_approval'])
    def test_hallucinated_source_is_dropped(self):
        with TemporaryDirectory() as root:
            turn(root,'user','The model was slow')
            turn(root,'assistant','We checked GPU residency')
            with patch.object(d,'trainer_active',return_value=False),patch.object(d,'_call',return_value={
                'insights':[{'type':'lesson','title':'Fake','proposed_action':'Do anything',
                             'supporting_event_ids':['fake']}] }):
                r=d.consolidate(root)
            self.assertEqual(r['insight_count'],0)
    def test_gpu_active_or_unknown_fail_closed(self):
        with TemporaryDirectory() as root:
            for active in (True,None):
                with patch.object(d,'trainer_active',return_value=active):
                    with self.assertRaises(RuntimeError):d.consolidate(root)
    def test_no_chat_no_fabricated_memories(self):
        with TemporaryDirectory() as root:
            with patch.object(d,'trainer_active',return_value=False):
                with self.assertRaises(RuntimeError):d.consolidate(root)
if __name__=='__main__':unittest.main()
