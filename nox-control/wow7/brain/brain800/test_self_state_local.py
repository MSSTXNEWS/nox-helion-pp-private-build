import json
import sqlite3
import unittest
import self_state as s

class FunctionalSelfTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        s.init(self.db)
    def obs(self,e,k,v=None):
        return s.observe(self.db,'Иван',str(e),k,'дикция',v)
    def test_learning_and_isolation(self):
        first=self.obs(1,'novelty')
        self.assertEqual(first['next_behavior'],'propose')
        latest=first
        for i in range(2,12,2):
            self.obs(i,'feedback',1 if latest['next_behavior'] in ('hold','question') else -1)
            latest=self.obs(i+1,'novelty')
        self.assertNotEqual(latest['next_behavior'],first['next_behavior'])
        self.assertLess(latest['learned_appraisal'],-0.9)
        self.assertEqual(s.reflect(self.db,'другой')['known'],[])
        db_dump=''.join(self.db.iterdump())
        self.assertNotIn('дикция',db_dump)
        self.assertNotIn('Иван',db_dump)
    def test_prediction_and_replay(self):
        prediction=self.obs(1,'prediction',0.9)
        self.assertEqual(self.obs(1,'prediction',0.9),prediction)
        self.obs(2,'outcome',0)
        reflected=s.reflect(self.db,'Иван')
        self.assertEqual(reflected['predictions_corrected'],1)
        self.assertEqual(reflected['known'][0]['episodes'],2)
        with self.assertRaises(ValueError): self.obs(2,'outcome',1)
        with self.assertRaises(ValueError): self.obs(3,'outcome',1)
        self.assertEqual(s.reflect(self.db,'Иван')['known'][0]['episodes'],2)
        json.dumps(reflected,allow_nan=False)
    def test_feedback_dedup(self):
        self.obs('a','novelty')
        a=self.obs('b','feedback',1)
        self.assertEqual(self.obs('b','feedback',1),a)
        with self.assertRaises(ValueError): self.obs('c','feedback',1)

if __name__=='__main__': unittest.main()
