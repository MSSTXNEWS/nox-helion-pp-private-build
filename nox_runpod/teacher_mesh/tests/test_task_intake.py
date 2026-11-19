import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nox_task_intake import load_tasks, propose_for_existing_scheduler

class TaskIntakeTests(unittest.TestCase):
    def test_manifest_no_duplicates(self):
        d=load_tasks()
        self.assertGreaterEqual(len(d["tasks"]),20)
        self.assertEqual(len({t["id"] for t in d["tasks"]}),len(d["tasks"]))
        self.assertTrue(d["policies"]["production_untouched"])
    def test_no_implicit_enqueue(self):
        self.assertEqual(propose_for_existing_scheduler(set())["jobs_enqueued"],0)
        p=propose_for_existing_scheduler({"INV-001"},stop_available=True,owner_approved=True)
        self.assertEqual(p["state"],"PROPOSAL_ONLY")
        self.assertEqual(p["jobs_enqueued"],0)
        self.assertEqual(p["skipped_existing"],1)

if __name__=="__main__": unittest.main()
