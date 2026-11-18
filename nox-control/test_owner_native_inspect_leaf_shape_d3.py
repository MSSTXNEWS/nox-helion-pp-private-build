#!/usr/bin/env python3
"""D3 regression: malformed untrusted leaf blockers never abort read-only queue inspection."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "owner_native_inspect_shape_d3", Path(__file__).with_name("owner_native_inspect.py"))
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


class LeafShapeReadOnlyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "nox"
        (self.root / "state" / "dispatcher").mkdir(parents=True)
        root_patch = patch.object(INSPECT, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def inspect(self, blocker_values, include_second=False):
        tasks = {}
        for index, blockers in enumerate(blocker_values):
            leaf = {"operation": "read_only", "blockers": blockers}
            receipt = {"worker_result": {
                "leaf_evidence": leaf,
                "leaf_evidence_sha256": hashlib.sha256(INSPECT.encoded(leaf)).hexdigest()
            }}
            tasks[str(index)] = {
                "id": str(index), "handler": "owner_native_typed_leaf", "status": "DONE",
                "result": {"receipt": receipt}
            }
        if include_second:
            leaf = {"operation": "read_only", "blockers": ["HOLD_RESOURCE_PRESSURE"]}
            tasks["second"] = {
                "id": "second", "handler": "owner_native_typed_leaf", "status": "DONE",
                "result": {"receipt": {"worker_result": {"leaf_evidence": leaf}}}
            }
        (self.root / "state" / "dispatcher" / "state.json").write_text(
            json.dumps({"tasks": tasks}), encoding="utf-8")
        stream = io.StringIO()
        with patch.object(INSPECT, "s03_receipt_check", return_value={"verified": False}):
            with contextlib.redirect_stdout(stream):
                INSPECT.leaf_queue_summary()
        rows = []
        for line in stream.getvalue().splitlines():
            if line.startswith("NOX_MAINT_SCOPE_POST_TASK="):
                rows.append(json.loads(line.split("=", 1)[1]))
        return rows, stream.getvalue()

    def test_valid_blocker_remains_visible(self):
        rows, output = self.inspect([["HOLD_RESOURCE_PRESSURE"]])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["leaf"]["blockers"], ["HOLD_RESOURCE_PRESSURE"])
        self.assertIs(rows[0]["leaf"]["blockers_schema_valid"], True)

    def test_empty_blockers_remain_empty(self):
        rows, _ = self.inspect([[]])
        self.assertEqual(rows[0]["leaf"]["blockers"], [])
        self.assertIs(rows[0]["leaf"]["blockers_schema_valid"], True)

    def test_malformed_blockers_are_unknown_not_empty_or_abort(self):
        for malformed in (None, "HOLD_RESOURCE_PRESSURE", {"bad": "shape"}, [None], ["bad!"], ["ok"] * 1001):
            with self.subTest(value_type=type(malformed).__name__):
                rows, _ = self.inspect([malformed])
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["leaf"]["blockers"], ["UNKNOWN_BLOCKERS_SCHEMA"])
                self.assertIs(rows[0]["leaf"]["blockers_schema_valid"], False)

    def test_bad_first_task_does_not_hide_next_task(self):
        rows, output = self.inspect([None], include_second=True)
        self.assertEqual(len(rows), 2)
        self.assertIn("NOX_MAINT_SCOPE_POST_QUEUE=", output)
        self.assertEqual(rows[0]["leaf"]["blockers"], ["UNKNOWN_BLOCKERS_SCHEMA"])
        self.assertEqual(rows[1]["leaf"]["blockers"], ["HOLD_RESOURCE_PRESSURE"])


class WorkerStatusShapeTests(unittest.TestCase):
    """A malformed native worker snapshot must not abort read-only inspection."""
    def sample(self, native):
        records = []
        def fake_process(pid):
            return {'pid': pid, 'ppid': 4, 'start_ticks': 42, 'state': 'S'}
        with patch.object(INSPECT, 'obj', return_value=({'native_subexecutors': native}, b'{}', None)):
            with patch.object(INSPECT, 'process', side_effect=fake_process):
                with patch.object(INSPECT, 'emit', side_effect=lambda name, value: records.append((name, value))):
                    INSPECT.worker_status_sample()
        self.assertEqual([name for name, _ in records], ['POST_WORKERS'])
        return records[0][1]

    def test_missing_workers_field_is_unknown(self):
        row = self.sample({'director': {}})
        self.assertIs(row['workers_schema_valid'], False)
        self.assertEqual(row['state'], 'UNKNOWN_WORKERS_SCHEMA')

    def test_null_or_dict_workers_is_explicit_unknown(self):
        for value in (None, {'bad': 'shape'}, 'bad', list(range(65))):
            with self.subTest(value_type=type(value).__name__):
                row = self.sample({'director': {}, 'workers': value})
                self.assertIs(row['workers_schema_valid'], False)
                self.assertEqual(row['state'], 'UNKNOWN_WORKERS_SCHEMA')

    def test_bad_worker_entry_is_preserved_as_unknown(self):
        row = self.sample({'director': {}, 'workers': [None, 12]})
        self.assertTrue(row['workers_schema_valid'])
        self.assertEqual(len(row['workers']), 2)
        self.assertTrue(all(x['state'] == 'UNKNOWN_WORKER_ENTRY' and not x['verified'] for x in row['workers']))

    def test_malformed_director_and_project_counts_fail_closed(self):
        row = self.sample({'director': 'invalid', 'workers': [],
                           'project_queues': {'queues': ['bad'], 'leaf_status': {'ok': 3, 'bool': True}}})
        self.assertIs(row['director_schema_valid'], False)
        self.assertIs(row['project']['queues_schema_valid'], False)
        self.assertEqual(row['project']['queues_state'], 'UNKNOWN_SCHEMA')
        self.assertEqual(row['project']['leaf_status'], {'ok': 3})

    def test_valid_worker_identity_still_verified(self):
        row = self.sample({'director': {'pid': 4, 'process_starttime': 42},
                           'workers': [{'pid': 5, 'ppid': 4, 'process_starttime': 42}]})
        self.assertIs(row['director_schema_valid'], True)
        self.assertIs(row['workers_schema_valid'], True)
        self.assertTrue(row['workers'][0]['verified'])


if __name__ == "__main__":
    unittest.main()
