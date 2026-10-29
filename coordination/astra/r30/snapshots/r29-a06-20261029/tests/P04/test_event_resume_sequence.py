"""P04 event monotonicity checks, synthetic event payloads only."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
def load():
    spec = importlib.util.spec_from_file_location("p04_events", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_resume_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            self.m.EventWriter(path,"run1","task1").emit("task.started","RUNNING","start","ok")
            resumed = self.m.EventWriter(path,"run1","task1")
            resumed.emit("task.progress","RUNNING","step","ok")
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([v["event_sequence"] for v in rows],[1,2])
            self.assertFalse(rows[-1]["evidence_verified"])

    def test_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"events.jsonl"
            self.m.EventWriter(path,"run1","task1").emit("task.started","RUNNING","start","ok")
            with self.assertRaises(ValueError):
                self.m.EventWriter(path,"run2","task1")
            with self.assertRaises(ValueError):
                self.m.EventWriter(path,"run1","task2")

    def test_invalid_metrics_do_not_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"events.jsonl"
            e=self.m.EventWriter(path,"run1","task1")
            for kw in ({"metric_value":float("nan")},{"numerator":True},{"denominator":-1}):
                with self.assertRaises(ValueError):
                    e.emit("task.progress","RUNNING","test","test",**kw)
            self.assertFalse(path.exists())
            e.emit("task.started","RUNNING","start","ok")
            self.assertEqual(e.sequence,1)

if __name__=="__main__":
    unittest.main()
