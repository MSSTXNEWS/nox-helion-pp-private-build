"""Bounded, digest-preserving transfer for owner native audit output."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("owner_native_operator.py")
SPEC = importlib.util.spec_from_file_location("owner_native_operator_transfer", SOURCE)
OP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(OP)

REQUEST_ID = 7004485291
SOURCE_SHA = "8ed43111ecc3be8c1b086d561304dfe581bddec5"


def audit_stdout(process_count: int = 8, process_complete: bool = True,
                 supervisor_complete: bool = True, gpu_complete: bool = True,
                 gpu_classification: str = "MATCHED") -> str:
    process_rows = [
        {
            "pid": pid + 100,
            "ppid": 1,
            "uid": 0,
            "start_ticks": pid + 200,
            "nspid": [pid + 100],
            "namespaces": {"pid": "pid:[4026531836]", "mnt": "mnt:[4026531841]", "cgroup": "cgroup:[4026531835]"},
            "comm": "fixture-native-worker-name",
            "exe": "fixture-native-executable-" + ("x" * 200),
            "exe_state": "AVAILABLE",
            "identity_state": "VERIFIED",
        }
        for pid in range(process_count)
    ]
    gpu_uuid = "GPU-12345678-1234-1234-1234-123456789abc"
    gpu_apps = [{"gpu_pid": 1964117, "gpu_uuid": gpu_uuid, "used_gpu_memory": 1024}]
    supervisor_services = {
        "return_code": 3,
        "command_rc": 3,
        "command_success": False,
        "inventory_complete": supervisor_complete,
        "rows_complete": supervisor_complete,
        "status_consistent": supervisor_complete,
        "truncated": False,
        "rejected_lines": 0,
        "duplicate_service_names": False,
        "identity_complete": True,
        "service_health": {"state": "DEGRADED", "counts": {"STOPPED": 1}, "running": 0, "not_running": 1},
        "services": [{"service": "nox-worker", "state": "STOPPED", "pid": None}],
    }
    gpu_link = {
        "gpu_pid": 1964117,
        "gpu_uuid": gpu_uuid,
        "evidence_state": "COMPLETE",
        "classification": gpu_classification,
        "identity_stability": "STABLE_BOTH",
        "visibility": "DIRECT_PROC",
    }
    sections = []
    for section in OP.AUDIT_SECTIONS:
        result = {}
        if section == "hardware":
            result = {
                "gpu_apps_before": {"return_code": 0, "complete": gpu_complete, "truncated": False,
                    "rejected_rows": 0, "unbounded": False, "apps": gpu_apps},
                "gpu_apps_after": {"return_code": 0, "complete": gpu_complete, "truncated": False,
                    "rejected_rows": 0, "unbounded": False, "apps": gpu_apps},
                "gpu_process_links": [gpu_link],
                "supervisor_services": supervisor_services,
            }
        row = {"section": section, "worker_pid": 1000 + len(sections), "result": result}
        if section == "process_rows":
            rows_sha = hashlib.sha256(json.dumps(process_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            truncated = not process_complete
            entries_seen = len(process_rows) + int(truncated)
            row["bounded_process_identity_inventory"] = {
                "scope": "ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY",
                "started_unix_ns": 100,
                "finished_unix_ns": 101,
                "entries_seen": entries_seen,
                "row_count": len(process_rows),
                "cap": 8192,
                "truncated": truncated,
                "enumeration_error": None,
                "read_failure_count": 0,
                "read_failure_pids": [],
                "complete": process_complete,
                "fields": ["pid", "ppid", "uid", "start_ticks", "nspid", "namespaces.pid",
                           "namespaces.mnt", "namespaces.cgroup", "comm", "exe", "exe_state"],
                "omitted_fields": ["argv", "cmdline", "environ", "cgroup_paths"],
                "rows_sha256": rows_sha,
                "rows": process_rows,
            }
        sections.append("NOX_MAINT_AUDIT=" + json.dumps(row, separators=(",", ":")))
    return "\n".join(sections + [OP.AUDIT_COMPLETE]) + "\n"


def transfer_records(marker_line: str):
    return OP.build_transfer_records(marker_line, REQUEST_ID, SOURCE_SHA, force=True)


class OwnerNativeOutputTransferTests(unittest.TestCase):
    def test_8192_process_rows_transfer_as_bounded_digest_checked_bundle(self):
        stdout = audit_stdout(8192)
        self.assertGreater(len(stdout.encode("utf-8")), 180_000)

        forwarded = OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)
        records = [line for line in forwarded if line.startswith(OP.TRANSFER_PREFIX)]
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(all(len(line.encode("utf-8")) < OP.MAX_FORWARD_LINE_BYTES for line in forwarded))
        restored = OP.reassemble_transfer_records(records, REQUEST_ID, SOURCE_SHA).decode("utf-8")
        self.assertEqual(restored, OP.audit_bundle_line(stdout))
        self.assertIn("NOX_MAINT_AUDIT_WORKERS_COMPLETE=true", forwarded)

        payload = restored.split("=", 1)[1]
        recovered_rows = [json.loads(line.split("=", 1)[1]) for line in payload.splitlines()]
        process_row = next(row for row in recovered_rows if row["section"] == "process_rows")
        self.assertEqual(len(process_row["bounded_process_identity_inventory"]["rows"]), 8192)
        status = OP.audit_census_status(stdout)
        self.assertTrue(status["process_census_complete"])
        self.assertTrue(status["supervisor_inventory_complete"])
        self.assertTrue(status["gpu_census_complete"])
        self.assertEqual(status["supervisor_command_rc"], 3)
        self.assertIs(status["supervisor_command_success"], False)
        self.assertEqual(status["supervisor_service_health"], "DEGRADED")
        self.assertEqual(status["gpu_pid_reconciliation"][0]["gpu_pid"], 1964117)
        self.assertEqual(status["gpu_pid_reconciliation"][0]["classification"], "MATCHED")

    def test_complete_marker_cannot_hide_missing_or_duplicate_worker_record(self):
        stdout = audit_stdout(2)
        lines = stdout.splitlines()
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join(lines[:-2] + lines[-1:]))

        duplicate = lines[:]
        duplicate[1] = duplicate[0]
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join(duplicate))

        early_complete = [lines[-1]] + lines[:-1]
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join(early_complete))

    def test_actual_inventory_shape_is_sha_checked_before_transfer(self):
        lines = audit_stdout(2).splitlines()
        process_index = OP.AUDIT_SECTIONS.index("process_rows")
        row = json.loads(lines[process_index].split("=", 1)[1])
        self.assertIn("bounded_process_identity_inventory", row)
        inventory = row["bounded_process_identity_inventory"]
        self.assertEqual(inventory["fields"], ["pid", "ppid", "uid", "start_ticks", "nspid",
            "namespaces.pid", "namespaces.mnt", "namespaces.cgroup", "comm", "exe", "exe_state"])
        self.assertIn("identity_state", inventory["rows"][0])
        self.assertIn("exe", inventory["rows"][0])

        inventory["rows_sha256"] = "0" * 64
        lines[process_index] = "NOX_MAINT_AUDIT=" + json.dumps(row, separators=(",", ":"))
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_SHA"):
            OP.forward_remote_stdout("\n".join(lines), "audit", REQUEST_ID, SOURCE_SHA)

    def test_audit_worker_error_is_not_accepted_as_complete_transfer(self):
        lines = audit_stdout(2).splitlines()
        storage_index = OP.AUDIT_SECTIONS.index("storage")
        lines[storage_index] = "NOX_MAINT_AUDIT=" + json.dumps(
            {"section": "storage", "error": "RuntimeError", "worker_pid": 1005},
            separators=(",", ":"),
        )
        stdout = "\n".join(lines)
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_WORKER_INCOMPLETE"):
            OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)

    def test_incomplete_process_supervisor_or_gpu_snapshot_is_forwarded_but_held(self):
        cases = (
            (audit_stdout(2, process_complete=False), "process_census_complete"),
            (audit_stdout(2, supervisor_complete=False), "supervisor_inventory_complete"),
            (audit_stdout(2, gpu_complete=False), "gpu_census_complete"),
            (audit_stdout(2, gpu_classification="NOT_VISIBLE"), "gpu_census_complete"),
        )
        for stdout, field in cases:
            with self.subTest(gate=field):
                forwarded = OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)
                self.assertIn("NOX_MAINT_AUDIT_WORKERS_COMPLETE=true", forwarded)
                status = OP.audit_census_status(stdout)
                self.assertFalse(status[field])
                with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_CENSUS_INCOMPLETE"):
                    OP.require_audit_census_complete(stdout)

    def test_oversized_non_audit_evidence_is_transferred_instead_of_dropped(self):
        marker = "NOX_MAINT_STORAGE_CENSUS=" + ("x" * 190_000)
        forwarded = OP.forward_remote_stdout(marker + "\n", "inspect", REQUEST_ID, SOURCE_SHA)
        restored = OP.reassemble_transfer_records(forwarded, REQUEST_ID, SOURCE_SHA)
        self.assertEqual(restored.decode("utf-8"), marker)
        self.assertTrue(all(len(line.encode("utf-8")) < OP.MAX_FORWARD_LINE_BYTES for line in forwarded))

    def test_missing_duplicate_swapped_truncated_or_corrupt_chunks_hold(self):
        records = transfer_records("NOX_MAINT_AUDIT_BUNDLE=" + ("z" * 180_000))
        variants = {
            "missing end": records[:-1],
            "duplicate": records[:2] + [records[1]] + records[2:],
            "swapped": records[:1] + [records[2], records[1]] + records[3:],
            "truncated": records[:2] + [records[1][:-5] + records[1][-1:]] + records[3:],
        }
        bad_digest = records[:]
        record_prefix, encoded = bad_digest[1].split("=", 1)
        chunk = json.loads(encoded)
        chunk["sha256"] = "0" * 64
        bad_digest[1] = record_prefix + "=" + json.dumps(chunk, separators=(",", ":"), sort_keys=True)
        variants["bad digest"] = bad_digest

        bad_count = records[:]
        for index in (0, len(bad_count) - 1):
            prefix, encoded = bad_count[index].split("=", 1)
            header = json.loads(encoded)
            header["chunk_count"] += 1
            bad_count[index] = prefix + "=" + json.dumps(header, separators=(",", ":"), sort_keys=True)
        variants["bad count"] = bad_count

        for label, variant in variants.items():
            with self.subTest(case=label), self.assertRaises(RuntimeError):
                OP.reassemble_transfer_records(variant, REQUEST_ID, SOURCE_SHA)

    def test_transfer_rejects_payload_above_eight_mib(self):
        marker = "NOX_MAINT_AUDIT_BUNDLE=" + ("x" * (OP.TRANSFER_MAX_BYTES + 1))
        with self.assertRaisesRegex(RuntimeError, "HOLD_TRANSFER_ARTIFACT_OVERSIZE"):
            transfer_records(marker)

    def test_source_or_request_mismatch_holds(self):
        records = transfer_records("NOX_MAINT_AUDIT_BUNDLE=" + ("z" * 180_000))
        with self.assertRaisesRegex(RuntimeError, "HOLD_TRANSFER_BOUNDARY_MISMATCH|HOLD_TRANSFER_METADATA_INVALID"):
            OP.reassemble_transfer_records(records, REQUEST_ID + 1, SOURCE_SHA)
        with self.assertRaisesRegex(RuntimeError, "HOLD_TRANSFER_BOUNDARY_MISMATCH|HOLD_TRANSFER_METADATA_INVALID"):
            OP.reassemble_transfer_records(records, REQUEST_ID, "a" * 40)


if __name__ == "__main__":
    unittest.main()
