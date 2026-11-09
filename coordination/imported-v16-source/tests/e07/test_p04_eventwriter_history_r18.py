#!/usr/bin/env python3
"""E07 independent SOURCE QA: P04 event ledger identity on full resume.
Runs without CUDA. By default imports real Packages/P04/train_qlora.py from checkout;
`--source` can point to the explicitly labelled SOURCE-DERIVED local extractor.

Not an attestation that events were emitted by real NVIDIA training.
"""
import argparse, importlib.util, json, pathlib, tempfile, unittest

P = argparse.ArgumentParser()
P.add_argument('--source', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2]/'Packages/P04/train_qlora.py')
ARGS, REMAINING = P.parse_known_args()
spec = importlib.util.spec_from_file_location('p04_event_module_r18', ARGS.source)
p04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p04)

class TestFullEventHistoryResume(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.folder.name)/'events.jsonl'
        w = p04.EventWriter(self.path, 'approved-run', 'P04-safe-task')
        for _ in range(3):
            w.emit('training.step','RUNNING','optimizer_step','one actual-source-derived test event')
        self.rows = [json.loads(row) for row in self.path.read_text().splitlines()]
    def tearDown(self):
        self.folder.cleanup()
    def mutate(self, ix, f):
        f(self.rows[ix])
        self.path.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in self.rows),encoding='utf-8')
    def verify_reject(self):
        with self.assertRaises(ValueError):
            p04.EventWriter(self.path,'approved-run','P04-safe-task')
    def test_positive_contiguous_resume(self):
        w = p04.EventWriter(self.path,'approved-run','P04-safe-task')
        self.assertEqual(w.sequence,3)
        w.emit('training.step','RUNNING','optimizer_step','resume')
        self.assertEqual(json.loads(self.path.read_text().splitlines()[-1])['event_sequence'],4)
    def test_negative_different_run_in_first_record(self):
        self.mutate(0,lambda r:r.__setitem__('run_id','foreign-run'))
        self.verify_reject()
    def test_negative_first_sequence_gap(self):
        self.mutate(0,lambda r:r.__setitem__('event_sequence',99))
        self.verify_reject()
    def test_negative_middle_sequence_duplicate(self):
        self.mutate(1,lambda r:r.__setitem__('event_sequence',1))
        self.verify_reject()
    def test_negative_duplicate_event_id(self):
        self.mutate(1,lambda r:r.__setitem__('event_id',self.rows[0]['event_id']))
        self.verify_reject()
    def test_negative_first_line_malformed_json(self):
        lines=self.path.read_text().splitlines()
        lines[0]='not JSON'
        self.path.write_text('\n'.join(lines)+'\n')
        self.verify_reject()
    def test_negative_last_entry_broken(self):
        self.mutate(-1,lambda r:r.__setitem__('run_id','foreign-run'))
        self.verify_reject()

if __name__=='__main__':
    unittest.main(argv=[__file__]+REMAINING,verbosity=2)
