import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import owner_native_gpu_inventory as gpu
import owner_native_operator as operator


SHA = "a" * 40
REQUEST = 7000000000
BOOT = "91e8d52f-1f5e-4c1c-a1fb-08dcf394f123"
GPU_A = "GPU-58f4970e-117b-ea29-9c68-b65c5ca88fd0"
GPU_B = "GPU-db9e6c65-6c6a-83c2-8304-e8605c5188bc"


def receipt():
    rows_a = [
        {"index": 0, "model": "Tesla V100-SXM2-32GB", "uuid": GPU_A,
         "memory_total_mib": 32768, "memory_used_mib": 16000, "memory_free_mib": 16768},
        {"index": 1, "model": "Tesla V100-SXM2-32GB", "uuid": GPU_B,
         "memory_total_mib": 32768, "memory_used_mib": 12000, "memory_free_mib": 20768},
    ]
    rows_b = copy.deepcopy(rows_a)
    rows_b[0]["memory_used_mib"] = 16100
    rows_b[0]["memory_free_mib"] = 16668
    inv = {
        "schema": "NOX_GPU_INVENTORY_V1",
        "action": "gpu_inventory",
        "instance_id": 60509551,
        "boot_id": BOOT,
        "uptime_scope": "two monotonic host snapshots; point-in-time only",
        "memory_semantics": "nvidia-smi MiB counters; memory.total=memory.used+memory.free",
        "identity_stable": True,
        "snapshots": [
            {"boot_id": BOOT, "uptime_seconds": 100.1, "monotonic_started_ns": 10,
             "monotonic_finished_ns": 20, "nvidia_smi_rc": 0, "rows": rows_a},
            {"boot_id": BOOT, "uptime_seconds": 101.1, "monotonic_started_ns": 30,
             "monotonic_finished_ns": 40, "nvidia_smi_rc": 0, "rows": rows_b},
        ],
    }
    return {
        "schema": "NOX_GPU_INVENTORY_V1",
        "action": "gpu_inventory",
        "instance_id": 60509551,
        "source_sha": SHA,
        "request_id": REQUEST,
        "inventory_sha256": gpu.inventory_digest(inv),
        "inventory": inv,
    }


def marker_lines(record=None):
    value = receipt() if record is None else record
    line = operator.GPU_INVENTORY_MARKER + json.dumps(value, sort_keys=True, separators=(",", ":"))
    return line + "\n" + operator.GPU_INVENTORY_COMPLETE


class OwnerGpuInventoryOperatorTests(unittest.TestCase):
    def test_action_route_and_embedded_payload_blob_pin(self):
        self.assertEqual(operator.FILES["gpu_inventory"],
                         "nox-control/owner_native_gpu_inventory.py")
        payload = operator._load_action_payload("gpu_inventory")
        self.assertIn("NOX_MAINT_GPU_INVENTORY_COMPLETE=true", payload)
        self.assertEqual(len(operator.GPU_INVENTORY_BLOB_SHA), 40)
        with patch.object(operator.Path, "read_text", return_value=payload + "# changed\n"):
            with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_PAYLOAD_PIN"):
                operator._load_action_payload("gpu_inventory")

    def test_exact_owner_request_and_source_checkout_are_required(self):
        event = {
            "repository": {"owner": {"id": operator.OWNER_ID}},
            "issue": {"number": 256},
            "sender": {"id": operator.OWNER_ID},
            "comment": {
                "id": REQUEST,
                "user": {"id": operator.OWNER_ID},
                "author_association": "OWNER",
                "body": f"/nox-maintain {operator.INSTANCE} {SHA} gpu_inventory",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_REPOSITORY": operator.REPO,
                "GITHUB_EVENT_NAME": "issue_comment",
                "NOX_PINNED_SOURCE_SHA": SHA,
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("owner_native_operator.subprocess.check_output", return_value=SHA + "\n"):
                    self.assertEqual(operator.authorize_event("gpu_inventory"), REQUEST)
                event["comment"]["body"] = f"/nox-maintain {operator.INSTANCE} {SHA} audit"
                event_path.write_text(json.dumps(event), encoding="utf-8")
                with patch("owner_native_operator.subprocess.check_output", return_value=SHA + "\n"):
                    with self.assertRaisesRegex(RuntimeError, "HOLD_EXACT_OWNER_COMMAND"):
                        operator.authorize_event("gpu_inventory")

    def test_forward_binds_receipt_to_exact_request_and_source(self):
        lines = marker_lines()
        forwarded = operator.forward_remote_stdout(lines, "gpu_inventory", REQUEST, SHA)
        self.assertEqual(forwarded, lines.splitlines())
        for req, source in ((REQUEST + 1, SHA), (REQUEST, "b" * 40)):
            with self.subTest(request=req, source=source):
                with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
                    operator.forward_remote_stdout(lines, "gpu_inventory", req, source)

    def test_forward_rejects_digest_shape_and_memory_mismatch(self):
        bad_digest = receipt()
        bad_digest["inventory_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(bad_digest), "gpu_inventory", REQUEST, SHA)
        bad_memory = receipt()
        bad_memory["inventory"]["snapshots"][0]["rows"][0]["memory_free_mib"] = 30000
        bad_memory["inventory_sha256"] = gpu.inventory_digest(bad_memory["inventory"])
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(bad_memory), "gpu_inventory", REQUEST, SHA)

    def test_forward_rejects_duplicate_markers_unknown_marker_and_bad_order(self):
        lines = marker_lines()
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_OUTPUT_SHAPE"):
            operator.forward_remote_stdout(lines + "\n" + operator.GPU_INVENTORY_COMPLETE,
                                           "gpu_inventory", REQUEST, SHA)
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_OUTPUT_SHAPE"):
            operator.forward_remote_stdout(operator.GPU_INVENTORY_COMPLETE + "\n" + lines.splitlines()[0],
                                           "gpu_inventory", REQUEST, SHA)
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_OUTPUT_SHAPE"):
            operator.forward_remote_stdout(lines + "\nNOX_MAINT_EXTRA=secret",
                                           "gpu_inventory", REQUEST, SHA)


    def test_forward_rejects_instance_model_nearmatch_and_under_sum_memory(self):
        bad_top_instance = receipt()
        bad_top_instance["instance_id"] = 60509552
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(bad_top_instance),
                                           "gpu_inventory", REQUEST, SHA)

        bad_nested_instance = receipt()
        bad_nested_instance["inventory"]["instance_id"] = 60509552
        bad_nested_instance["inventory_sha256"] = gpu.inventory_digest(
            bad_nested_instance["inventory"]
        )
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(bad_nested_instance),
                                           "gpu_inventory", REQUEST, SHA)

        near_match_model = receipt()
        near_match_model["inventory"]["snapshots"][0]["rows"][0]["model"] = (
            "Tesla V100-SXM2-32GB (rev A)"
        )
        near_match_model["inventory_sha256"] = gpu.inventory_digest(
            near_match_model["inventory"]
        )
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(near_match_model),
                                           "gpu_inventory", REQUEST, SHA)

        under_sum_memory = receipt()
        under_sum_memory["inventory"]["snapshots"][0]["rows"][0][
            "memory_free_mib"
        ] = 16000
        under_sum_memory["inventory_sha256"] = gpu.inventory_digest(
            under_sum_memory["inventory"]
        )
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(marker_lines(under_sum_memory),
                                           "gpu_inventory", REQUEST, SHA)


    def test_remote_success_requires_zero_exit_and_valid_receipt_schema(self):
        lines = marker_lines()
        self.assertIsNone(operator._gpu_inventory_remote_failure(lines, "unused", 0))
        self.assertEqual(
            operator.forward_remote_stdout(lines, "gpu_inventory", REQUEST, SHA),
            lines.splitlines(),
        )

        changed = receipt()
        changed["inventory"]["instance_id"] = 60509552
        changed["inventory_sha256"] = gpu.inventory_digest(changed["inventory"])
        changed_lines = marker_lines(changed)
        self.assertIsNone(operator._gpu_inventory_remote_failure(changed_lines, "", 0))
        with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_RECEIPT_SCHEMA"):
            operator.forward_remote_stdout(
                changed_lines, "gpu_inventory", REQUEST, SHA
            )

        nonzero = operator._gpu_inventory_remote_failure(lines, "private stderr", 2)
        self.assertEqual(
            nonzero["hold"], "HOLD_GPU_INVENTORY_RESULT_MISSING"
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_ORIGIN=REMOTE_HELPER",
            nonzero["records"],
        )

    def test_remote_helper_hold_is_propagated_with_only_fixed_codes(self):
        helper_hold = "HOLD_GPU_INVENTORY_NVIDIA_SMI_RC"
        stdout = (
            operator.GPU_INVENTORY_RESULT_PREFIX + helper_hold
            + "\nprivate stdout sentinel"
        )
        failure = operator._gpu_inventory_remote_failure(
            stdout, "private stderr sentinel", 2
        )
        self.assertEqual(failure["hold"], helper_hold)
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_ORIGIN=REMOTE_HELPER",
            failure["records"],
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_REMOTE_EXIT_CODE=2",
            failure["records"],
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=HELPER_HOLD",
            failure["records"],
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_HELPER_HOLD=" + helper_hold,
            failure["records"],
        )
        self.assertNotIn("private stdout sentinel", str(failure))
        self.assertNotIn("private stderr sentinel", str(failure))

    def test_ssh_nonzero_and_missing_helper_marker_are_distinct_and_sanitized(self):
        ssh = operator._gpu_inventory_remote_failure(
            "NOX_MAINT_SECRET=stdout-secret-sentinel",
            "Permission denied (publickey): stderr-secret-sentinel",
            255,
        )
        self.assertEqual(ssh["hold"], "HOLD_GPU_INVENTORY_SSH_FAILURE")
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_ORIGIN=SSH", ssh["records"]
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_REMOTE_EXIT_CODE=255", ssh["records"]
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=SSH_AUTH_REJECTED",
            ssh["records"],
        )
        self.assertNotIn("stdout-secret-sentinel", str(ssh))
        self.assertNotIn("stderr-secret-sentinel", str(ssh))

        missing = operator._gpu_inventory_remote_failure(
            "NOX_MAINT_GPU_INVENTORY_COMPLETE=true\n"
            "NOX_MAINT_SECRET=missing-result-secret",
            "private stderr sentinel",
            2,
        )
        self.assertEqual(missing["hold"], "HOLD_GPU_INVENTORY_RESULT_MISSING")
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_ORIGIN=REMOTE_HELPER",
            missing["records"],
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=REMOTE_RESULT_MISSING",
            missing["records"],
        )
        self.assertNotIn("missing-result-secret", str(missing))
        self.assertNotIn("private stderr sentinel", str(missing))

    def test_malformed_or_mismatched_helper_result_markers_hold_closed(self):
        helper_line = (
            operator.GPU_INVENTORY_RESULT_PREFIX
            + "HOLD_GPU_INVENTORY_NVIDIA_SMI_RC"
        )
        duplicate = operator._gpu_inventory_remote_failure(
            helper_line + "\n" + helper_line, "", 2
        )
        self.assertEqual(
            duplicate["hold"], "HOLD_GPU_INVENTORY_HELPER_RESULT_SHAPE"
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=MALFORMED_HELPER_OUTPUT",
            duplicate["records"],
        )

        unknown = operator._gpu_inventory_remote_failure(
            operator.GPU_INVENTORY_RESULT_PREFIX
            + "HOLD_GPU_INVENTORY_SECRET_SENTINEL",
            "unused",
            2,
        )
        self.assertEqual(unknown["hold"], "HOLD_GPU_INVENTORY_HELPER_FAILURE")
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=UNRECOGNIZED_HELPER_HOLD",
            unknown["records"],
        )
        self.assertNotIn("SECRET_SENTINEL", str(unknown))

        wrong_exit = operator._gpu_inventory_remote_failure(helper_line, "", 0)
        self.assertEqual(
            wrong_exit["hold"], "HOLD_GPU_INVENTORY_HELPER_EXIT_MISMATCH"
        )
        self.assertIn(
            "NOX_MAINT_GPU_INVENTORY_FAILURE_CLASS=HELPER_EXIT_MISMATCH",
            wrong_exit["records"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
