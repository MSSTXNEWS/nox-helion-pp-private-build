"""No-download unit checks for SOUL Stage-1 trainer. Never touch real S03."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from nox_prime_soul_stage1_train import GROUPS, featurize,parse_split,score,baseline

class Stage1Tests(unittest.TestCase):
    def test_six_cognitive_categories(self):
        self.assertEqual(len(GROUPS),6)
        self.assertIn("curiosity",GROUPS)
        self.assertIn("neutral",GROUPS)
    def test_hashing_deterministic(self):
        a=featurize("This is interesting!")
        self.assertEqual(a,featurize("THIS IS INTERESTING!"))
        self.assertGreater(len(a),1)
        self.assertTrue(all(0<=v<16384 for v in a))
    def test_parse_official_tsv(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"test.tsv"
            p.write_text("I am curious\t7\tunique_A\nThank you\t15\tunique_B\n",encoding="utf-8")
            rows=parse_split(p)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][1][list(GROUPS).index("curiosity")],1)
        self.assertEqual(rows[1][1][list(GROUPS).index("positive")],1)
    def test_reject_duplicates(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"test.tsv"
            p.write_text("A\t27\tx\nB\t27\tx\n",encoding="utf-8")
            with self.assertRaises(RuntimeError):
                parse_split(p)
    def test_reject_bad_labels(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"test.tsv"
            p.write_text("A\t999\tx\n",encoding="utf-8")
            with self.assertRaises(RuntimeError):
                parse_split(p)
    def test_metrics(self):
        truth=[[1,0,0,0,0,0],[0,0,0,0,0,1]]
        probs=[[.9,.1,0,0,0,.1],[0,0,0,0,0,.8]]
        self.assertEqual(score(probs,truth,.5),1)
        self.assertLess(baseline(truth),1)
if __name__=="__main__": unittest.main()
