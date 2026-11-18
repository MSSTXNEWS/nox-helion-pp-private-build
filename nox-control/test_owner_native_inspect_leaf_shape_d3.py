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


if __name__ == "__main__":
    unittest.main()
