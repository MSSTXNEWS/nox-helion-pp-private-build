#!/usr/bin/env python3
"""Fixture tests for the privacy-bounded active queue diagnostic."""
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("owner_native_inspect.py")
SPEC = importlib.util.spec_from_file_location("owner_native_inspect", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ActiveQueueReadbackTests(unittest.TestCase):
    def test_running_row_allowlists_and_hashes_without_private_payload(self):
        claim = {"pid": 42, "worker": "runtime", "nonce": "do-not-print"}
        tasks = {"owner.task_a": {
            "id": "owner.task_a", "handler": "owner_native_project_work",
            "status": "RUNNING", "queue_id": "qA", "parent_task_id": "parent-A",
            "owner_claim": claim,
            "params": {"operation_key": "op-A", "prompt": "private prompt"},
            "result": {"receipt": None},
        }}
        report = MODULE.safe_active_queue_rows(tasks)
        row = report["rows"][0]
        output = json.dumps(report, sort_keys=True)
        self.assertEqual(report["running_count"], 1)
        self.assertEqual(row["task_id"], "owner.task_a")
        self.assertEqual(row["operation_key"], "UNKNOWN")
        self.assertEqual(row["operation_key_sha256"], MODULE.hashlib.sha256(b"op-A").hexdigest())
        self.assertEqual(row["operation_key_state"], "HASHED")
        self.assertEqual(row["claim_sha256"], MODULE.hashlib.sha256(
            json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False).encode()).hexdigest())
        self.assertEqual(row["terminal_receipt_state"], "UNKNOWN_NO_RECEIPT")
        self.assertEqual(row["s03_state"], "UNKNOWN_NOT_VERIFIED_BY_INSPECTOR")
        for private in ("do-not-print", "private prompt", "nonce", "params"):
            self.assertNotIn(private, output)

    def test_receipt_is_hash_only_and_does_not_claim_s03_verification(self):
        claim = {"pid": 8, "worker": "memory", "nonce": "hidden"}
        receipt = {"schema": "NOX_TEST", "phase": "terminal", "task_id": "owner.task_b",
                   "job_id": "job-B", "claim": claim, "private_text": "must not leak"}
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
        report = MODULE.safe_active_queue_rows({
            "owner.task_b": {"id": "owner.task_b", "handler": "leaf", "status": "running",
                       "owner_claim": claim, "params": {"prompt": "private"},
                       "result": {"receipt": receipt,
                                  "receipt_sha256": MODULE.hashlib.sha256(raw).hexdigest()}},
            "idle": {"id": "idle", "status": "pending", "params": {"prompt": "hidden"}},
        })
        row = report["rows"][0]
        self.assertEqual(row["receipt_hash_matches"], True)
        self.assertRegex(row["receipt_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(row["s03_state"], "UNKNOWN_NOT_VERIFIED_BY_INSPECTOR")
        for private in ("private_text", "must not leak", "hidden"):
            self.assertNotIn(private, json.dumps(row))

    def test_free_text_operation_key_and_task_id_are_never_emitted(self):
        private_text = "private client meeting notes"
        tasks = {
            private_text: {
                "id": private_text, "handler": "leaf", "status": "running",
                "params": {"operation_key": private_text, "prompt": private_text},
            }
        }
        report = MODULE.safe_active_queue_rows(tasks)
        row = report["rows"][0]
        encoded = json.dumps(report, sort_keys=True)
        self.assertEqual(row["task_id"], "UNKNOWN")
        self.assertEqual(row["task_id_state"], "UNKNOWN")
        self.assertEqual(row["task_id_sha256"],
                         MODULE.hashlib.sha256(private_text.encode()).hexdigest())
        self.assertEqual(row["operation_key"], "UNKNOWN")
        self.assertEqual(row["operation_key_state"], "HASHED")
        self.assertEqual(row["operation_key_sha256"],
                         MODULE.hashlib.sha256(private_text.encode()).hexdigest())
        self.assertNotIn(private_text, encoded)

    def test_cap_invalid_shape_and_unknown_fields_are_explicit(self):
        tasks = {f"task-{i:03}": {"id": f"task-{i:03}", "status": "running",
                                  "params": {"x": "y"}} for i in range(40)}
        report = MODULE.safe_active_queue_rows(tasks, row_cap=3)
        self.assertEqual(report["running_count"], 40)
        self.assertEqual(len(report["rows"]), 3)
        self.assertTrue(report["rows_truncated"])
        self.assertEqual(MODULE.safe_active_queue_rows([], row_cap=3)["state"],
                         "HOLD_INVALID_QUEUE")
        self.assertEqual(MODULE.safe_active_queue_rows({}, row_cap=0)["state"],
                         "HOLD_INVALID_ROW_CAP")
        self.assertEqual(report["rows"][0]["operation_key_state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
