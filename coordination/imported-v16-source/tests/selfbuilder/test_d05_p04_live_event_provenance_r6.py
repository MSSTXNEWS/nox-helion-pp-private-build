"""Original P04 live event relay: real temporary files, no model/GPU/E07 claims."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from src.nox_selfbuilder.background_forge import ExistingP04Background, ForgeHold

class D05LiveEventTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        self.path = root / 'events.jsonl'
        self.sent = []
        self.job = SimpleNamespace(run_id='r1', task_id='t1')
        owner = object.__new__(ExistingP04Background)
        owner._control = lambda job: root
        owner._relayed = set()
        owner.trainer = SimpleNamespace(reject_reparse_ancestors=lambda path: None,
                                        EventWriter=lambda *args: None)
        owner.event_sink = lambda row: self.sent.append(row) or True
        self.owner = owner

    def event(self, seq=1, **updates):
        item = dict(schema='NOX-INSTALLER-EVENT-v3', run_id='r1', task_id='t1',
                    package_id='P04', source='P04.QLoRA', evidence_verified=False,
                    event_sequence=seq, event_id=f'{seq:032x}', event_type='task.progress',
                    state='RUNNING', message='gpu step', metric_value=0.5)
        item.update(updates)
        return json.dumps(item, separators=(',', ':'))

    def test_valid_live_events_forward_once(self):
        self.path.write_text(self.event(1)+'\n'+self.event(2)+'\n', encoding='utf-8')
        self.assertEqual(self.owner.relay_events(self.job, live=True), 2)
        self.assertEqual(self.owner.relay_events(self.job, live=True), 0)

    def test_duplicate_control_key_is_hold(self):
        raw = self.event().replace('"state":"RUNNING"', '"state":"STOPPED","state":"RUNNING"')
        self.path.write_text(raw+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ForgeHold, 'P04_EVENT_AMBIGUOUS_JSON_HOLD'):
            self.owner.relay_events(self.job, live=True)
        self.assertFalse(self.sent)

    def test_nonfinite_and_reordered_rows_are_hold(self):
        raw = self.event().replace('"metric_value":0.5', '"metric_value":NaN')
        self.path.write_text(raw+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ForgeHold, 'P04_EVENT_NONFINITE_HOLD'):
            self.owner.relay_events(self.job, live=True)
        self.path.write_text(self.event(2)+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ForgeHold, 'P04_EVENT_PROVENANCE_HOLD'):
            self.owner.relay_events(self.job, live=True)
        self.assertFalse(self.sent)

    def test_partial_trailing_row_is_not_forwarded(self):
        self.path.write_text(self.event(1)+'\n'+self.event(2)[:-3], encoding='utf-8')
        self.assertEqual(self.owner.relay_events(self.job, live=True), 1)

    def test_completed_not_forwarded_before_native_s03(self):
        self.path.write_text(self.event(1, state='COMPLETED', event_type='task.completed')+'\n', encoding='utf-8')
        self.assertEqual(self.owner.relay_events(self.job, live=True), 0)
        self.assertEqual(self.owner.relay_events(self.job, durable_s03=False), 0)
        self.assertEqual(self.owner.relay_events(self.job, durable_s03=True), 1)

if __name__ == '__main__':
    unittest.main()
