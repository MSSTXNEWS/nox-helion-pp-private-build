"""Regression: owner-native inspection must never publish private S03/task payloads.

Synthetic, local-only tests. No OneHost access, model load, credentials, or cleanup.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_owner_native_inspect_leaf_shape_d3 import LeafShapeReadOnlyTests  # D3 queue shape gate

SPEC = importlib.util.spec_from_file_location(
    "nox_inspect_privacy_under_test", Path(__file__).with_name("owner_native_legacy_inspect.py"))
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)


class ReceiptPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "state/owner_components").mkdir(parents=True)
        (self.root / "state/dispatcher").mkdir(parents=True)
        self.scope = patch.object(INSPECT, "ROOT", self.root)
        self.scope.start()

    def tearDown(self):
        self.scope.stop()
        self.tmp.cleanup()

    def test_receipt_summarizes_without_secrets(self):
        p = self.root / "state/owner_maintenance_001.json"
        p.write_text(json.dumps({"schema": "NOX_SAFE", "state": "PASS",
                                 "successful_optimizer_steps": 6,
                                 "secret": "DO_NOT_PUBLISH_THIS_SECRET",
                                 "result": {"message": "private owner conversation"}}))
        data = INSPECT.receipts()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["evidence"]["fields"]["successful_optimizer_steps"], 6)
        self.assertEqual(data[0]["evidence"]["fields"]["state"], "PASS")
        self.assertNotIn("private owner conversation", str(data))
        self.assertNotIn("DO_NOT_PUBLISH_THIS_SECRET", str(data))
        self.assertIn("sha256", data[0]["evidence"])

    def test_queue_withholds_results_and_claim_text(self):
        task = {"id": "owner.review.abc123", "status": "blocked",
                "result_state": "HOLD_RESOURCE", "retries": 1,
                "claimed_by": "confidential@example.test",
                "result": {"private": "OWNER_PROMPT_DO_NOT_PRINT"}}
        queue = self.root / "state/dispatcher/state.json"
        queue.write_text(json.dumps({"tasks": {"owner.review.abc123": task}}))
        evidence = self.root / "state/owner_components/owner.memory.json"
        evidence.write_text(json.dumps({"schema": "S03_STATUS_V1", "status": "HOLD",
                                        "secret": "S03_PRIVATE_TOKEN_DO_NOT_PRINT"}))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            INSPECT.owner_component_readback()
        text = buf.getvalue()
        self.assertIn("OWNER_TASK_STATUS_ONLY_NO_RESULTS", text)
        self.assertIn("owner.review.abc123", text)
        self.assertIn("result_payload_withheld", text)
        for forbidden in ("OWNER_PROMPT_DO_NOT_PRINT", "confidential@example.test",
                          "S03_PRIVATE_TOKEN_DO_NOT_PRINT"):
            self.assertNotIn(forbidden, text)

    def test_symlink_never_follows_owner_receipt(self):
        secret = self.root / "secret.txt"
        secret.write_text("PRIVATE_FILE")
        link = self.root / "state/owner_maintenance_002.json"
        link.symlink_to(secret)
        self.assertEqual(INSPECT.bounded_receipt_meta(link)["state"], "HOLD_SYMLINK")

    def test_duplicate_keys_and_invalid_json_fail_closed(self):
        p = self.root / "state/owner_maintenance_003.json"
        p.write_text('{"state":"PASS","state":"HOLD"}')
        self.assertEqual(INSPECT.bounded_receipt_meta(p)["state"], "HOLD_INVALID_JSON")
        p.write_text('{"state":NaN}')
        self.assertEqual(INSPECT.bounded_receipt_meta(p)["state"], "HOLD_INVALID_JSON")
        p.write_text("[1,2,3]")
        self.assertEqual(INSPECT.bounded_receipt_meta(p)["state"], "HOLD_INVALID_OBJECT")

    def test_file_bound_and_non_regular_fail_closed(self):
        p = self.root / "state/owner_maintenance_004.json"
        p.write_bytes(b"x" * 100001)
        self.assertEqual(INSPECT.bounded_receipt_meta(p)["state"], "HOLD_FILE_BOUND")

    def test_reject_untrusted_status_strings_and_bool_retry(self):
        bad = {"id": "owner.review.abc123", "status": "password=SECRET",
               "result_state": "HOLD_SAFE", "retries": True}
        row = INSPECT.safe_owner_task(bad)
        self.assertNotIn("status", row)
        self.assertNotIn("retries", row)
        self.assertEqual(row["result_state"], "HOLD_SAFE")


    def test_qwen_progress_never_leaks_private_text_or_invalid_metrics(self):
        run = self.root / "lora/qwen35_9b/20261116_01"
        run.mkdir(parents=True)
        (run / "owner_last_result.json").write_text(json.dumps({
            "schema": "NOX_QWEN_PROGRESS_V1",
            "state": "HOLD_TRAINING",
            "reason": "private S03 dialogue must not print",
            "error": "password=PERSONAL_SECRET_EXAMPLE",
            "request": "owner-private-conversation-identifier",
            "successful_optimizer_steps": 8,
            "step": True,
            "loss": None,
            "finished_at": "private_timestamp_or_chat_text"
        }))
        rows = INSPECT.qwen_training_readback()
        hit = next(row for row in rows if row.get("receipt") == "owner_last_result.json")
        fields = hit["fields"]
        self.assertEqual(hit["scope"], "SELF_REPORTED_NOT_LIVE_PROOF")
        self.assertEqual(fields["successful_optimizer_steps"], 8)
        self.assertEqual(fields["state"], "HOLD_TRAINING")
        for key in ("error", "reason", "request", "step", "loss", "finished_at"):
            self.assertNotIn(key, fields)
        self.assertNotIn("private S03", str(rows))
        self.assertNotIn("PERSONAL_SECRET", str(rows))

    def test_qwen_duplicate_and_nonfinite_receipts_fail_closed(self):
        run = self.root / "lora/qwen35_9b/20261116_02"
        run.mkdir(parents=True)
        receipt = run / "owner_progress.json"
        malformed = (
            '{"state":"RUNNING","successful_optimizer_steps":25,"successful_optimizer_steps":2500}',
            '{"state":"RUNNING","metadata":{"revision":"original","revision":"swapped"},"successful_optimizer_steps":25}',
            '{"state":"RUNNING","successful_optimizer_steps":25,"loss":NaN}',
            '{"state":"RUNNING","successful_optimizer_steps":25,"loss":Infinity}',
        )
        for payload in malformed:
            with self.subTest(payload=payload[:32]):
                receipt.write_text(payload)
                rows = INSPECT.qwen_training_readback()
                hit = next(row for row in rows if row.get("receipt") == "owner_progress.json")
                self.assertEqual(hit["state"], "READ_OR_PARSE_HOLD")
                self.assertNotIn("fields", hit)
                self.assertNotIn("successful_optimizer_steps", str(hit))
        receipt.write_text('{"state":"HOLD_TRAINING","successful_optimizer_steps":25,"loss":1.25}')
        rows = INSPECT.qwen_training_readback()
        hit = next(row for row in rows if row.get("receipt") == "owner_progress.json")
        self.assertEqual(hit["state"], "METADATA_READ_ONLY")
        self.assertEqual(hit["fields"]["successful_optimizer_steps"], 25)

    def test_qwen_status_codes_and_finite_metrics_are_bounded(self):
        fields = INSPECT.safe_qwen_receipt_fields({
            "request": "6908923245", "schema": "NOX_QWEN_PROGRESS_V1",
            "optimizer_steps_verified": False, "successful_updates": 8,
            "loss": 1.25, "reason": "HOLD_BACKUP", "step": -3,
            "updated_at": float("inf"), "checkpoint_verified": "true"
        })
        self.assertEqual(fields["request"], "6908923245")
        self.assertEqual(fields["successful_updates"], 8)
        self.assertEqual(fields["loss"], 1.25)
        self.assertEqual(fields["reason"], "HOLD_BACKUP")
        self.assertIs(fields["optimizer_steps_verified"], False)
        for key in ("step", "updated_at", "checkpoint_verified"):
            self.assertNotIn(key, fields)


    def test_pinned_sftconfig_signature_rejects_ambiguous_duplicate_fields(self):
        # The exact native TRL constructor must never be declared compatible
        # from a JSON report with duplicate keys, even if the values match.
        valid = (
            '{"schema":"NOX_SFTCONFIG_NATIVE_SIGNATURE_V1",'
            '"trl_version":"1.18.0",'
            '"missing_required_kwargs":[],'
            '"save_safetensors_parameter":false}'
        )
        prefix = "NOX_SFTCONFIG_SIGNATURE="
        good = INSPECT.parse_sftconfig_signature_probe(0, prefix + valid)
        self.assertEqual(good["status"], "LEGACY_TRUE_REQUIRES_SAFE_OMISSION")
        for bad in (
            valid[:-1] + ',"save_safetensors_parameter":true}',
            valid[:-1] + ',"save_safetensors_parameter":false}',
            valid[:-1] + ',"trl_version":"1.18.0"}',
            valid[:-1] + ',"missing_required_kwargs":[]}',
            valid[:-1] + ',"schema":"NOX_SFTCONFIG_NATIVE_SIGNATURE_V1"}',
            valid.replace('"missing_required_kwargs":[]',
                          '"missing_required_kwargs":[NaN]'),
            valid.replace('"missing_required_kwargs":[]',
                          '"missing_required_kwargs":[Infinity]'),
        ):
            with self.subTest(case=bad[-70:]):
                result = INSPECT.parse_sftconfig_signature_probe(0, prefix + bad)
                self.assertEqual(result["status"], "HOLD_NATIVE_TRL_SIGNATURE_SCHEMA")
                self.assertNotIn("trl_version", result)
                self.assertEqual(result["optimizer_updates"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
