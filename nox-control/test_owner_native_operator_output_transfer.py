"""Bounded, digest-preserving transfer for owner native audit output."""
from __future__ import annotations

import hashlib
import importlib.util
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
GPU_PID = 1964117
GPU_UUID = "GPU-12345678-1234-1234-1234-123456789abc"
NS = {"pid": "pid:[4026531836]", "mnt": "mnt:[4026531841]", "cgroup": "cgroup:[4026531835]"}


def _proc_row(pid: int) -> dict:
    return {
        "pid": pid, "ppid": 1, "uid": 1000, "start_ticks": pid + 1000,
        "nspid": [pid], "namespaces": dict(NS), "comm": "fixture-worker",
        "exe": "fixture-worker", "exe_state": "AVAILABLE", "identity_state": "VERIFIED",
    }


def _proc_identity(pid: int) -> dict:
    row = _proc_row(pid)
    return {
        "pid": pid, "start_ticks": row["start_ticks"], "nspid": row["nspid"],
        "nspid_available": True, "pid_namespace": NS["pid"], "mnt_namespace": NS["mnt"],
        "cgroup_namespace": NS["cgroup"], "identity_state": "VERIFIED", "comm": "fixture-worker",
        "cgroups": ["/secret/cgroup/path-that-must-not-forward"],
    }


def _inventory(rows: list[dict], *, complete: bool = True) -> dict:
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "scope": "ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY", "started_unix_ns": 100,
        "finished_unix_ns": 101, "entries_seen": len(rows) + int(not complete),
        "row_count": len(rows), "cap": 8192, "truncated": not complete,
        "enumeration_error": None, "read_failure_count": 0, "read_failure_pids": [],
        "complete": complete,
        "fields": ["pid", "ppid", "uid", "start_ticks", "nspid", "namespaces.pid",
                   "namespaces.mnt", "namespaces.cgroup", "comm", "exe", "exe_state"],
        "omitted_fields": ["argv", "cmdline", "environ", "cgroup_paths"],
        "rows_sha256": digest, "rows": rows,
    }


def _fixture(process_count: int = 8, *, process_complete: bool = True,
             supervisor_complete: bool = True, gpu_complete: bool = True,
             gpu_classification: str = "MATCHED") -> str:
    # The exact source producer returns a keyword/GPU-filtered LIST plus the
    # separate all-PID identity inventory. Its arguments/scripts are sensitive
    # and must never be included in the forwarded bundle.
    pids = sorted([GPU_PID] + list(range(2, process_count + 1)))[:process_count]
    rows = [_proc_row(pid) for pid in pids]
    gpu_row = next(row for row in rows if row["pid"] == GPU_PID)
    gpu_identity = _proc_identity(GPU_PID)
    gpu_consumer = {
        "pid": GPU_PID, "comm": "fixture-worker", "executable": "python3",
        "arguments": [["-c", "SECRET_INLINE_CODE_SHOULD_NOT_FORWARD"]],
        "gpu_consumer": True, "start_ticks": gpu_identity["start_ticks"],
        "gpu_identity": {
            "gpu_pid": GPU_PID, "start_ticks": gpu_identity["start_ticks"], "nspid": [GPU_PID],
            "pid_namespace": NS["pid"], "mnt_namespace": NS["mnt"], "cgroup_namespace": NS["cgroup"],
            "classification": gpu_classification, "visibility": "DIRECT_PROC",
        },
        "scripts": ["/secret/storage/path/training.py"],
    }
    filtered_rows = [gpu_consumer, {
        "pid": 301, "comm": "python", "executable": "python3", "arguments": [],
        "gpu_consumer": False, "start_ticks": 1301, "scripts": ["/secret/script.py"],
    }]
    gpu_apps = [{"gpu_pid": GPU_PID, "gpu_uuid": GPU_UUID, "used_gpu_memory": "1024"}]
    running = {"service": "nox-model", "state": "RUNNING", "pid": GPU_PID,
               "identity_state": "VERIFIED", "identity": gpu_identity}
    stopped = {"service": "nox-worker-stopped", "state": "STOPPED", "pid": None,
               "identity": None}
    services = {
        "return_code": 3, "command_rc": 3, "command_success": False,
        "inventory_complete": supervisor_complete, "rows_complete": supervisor_complete,
        "status_consistent": supervisor_complete, "truncated": False, "rejected_lines": 0,
        "duplicate_service_names": False, "identity_complete": True,
        "service_health": {"state": "DEGRADED", "counts": {"RUNNING": 1, "STOPPED": 1},
                           "running": 1, "not_running": 1},
        "services": [running, stopped],
    }
    gpu_link = {
        "gpu_pid": GPU_PID, "gpu_uuid": GPU_UUID, "used_gpu_memory_before": "1024",
        "used_gpu_memory_after": "1024", "inventory_presence": "BOTH",
        "identity_stability": "STABLE_BOTH", "classification": gpu_classification,
        "evidence_state": "COMPLETE", "visibility": "DIRECT_PROC",
        "proc_identity": gpu_identity,
        "service_match": {"service": "nox-model", "pid": GPU_PID, "state": "RUNNING",
                           "relation": "DIRECT_PID", "start_ticks": gpu_identity["start_ticks"]},
        "parent_chain": [{"pid": GPU_PID, "ppid": 1, "start_ticks": gpu_identity["start_ticks"],
                          "comm": "fixture-worker", "pid_namespace": NS["pid"],
                          "cgroups": ["/secret/cgroup/path"]}],
        "before_alias_scan_complete": True, "after_alias_scan_complete": True,
        "scope": "READ_ONLY_GPU_PID_TO_PROC_SERVICE",
    }
    sections = []
    for index, section in enumerate(OP.AUDIT_SECTIONS):
        result = {}
        if section == "hardware":
            result = {
                "gpu_apps_before": {"return_code": 0, "started_unix_ns": 100, "finished_unix_ns": 101,
                    "complete": gpu_complete, "truncated": False, "rejected_rows": 0,
                    "unbounded": False, "scope": "NVIDIA_SMI_COMPUTE_APP_SNAPSHOT", "apps": gpu_apps},
                "gpu_apps_after": {"return_code": 0, "started_unix_ns": 102, "finished_unix_ns": 103,
                    "complete": gpu_complete, "truncated": False, "rejected_rows": 0,
                    "unbounded": False, "scope": "NVIDIA_SMI_COMPUTE_APP_SNAPSHOT", "apps": gpu_apps},
                "gpu_process_links": [gpu_link], "supervisor_services": services,
                "disk": {"/workspace": {"path": "/secret/storage/unrelated"}},
            }
        elif section == "process_rows":
            result = filtered_rows
        elif section == "supervisor":
            result = {"available": True, "owner_fence_readonly": {"markers": {"STOP": "NOT_PRESENT"}},
                      "results": [{"config": "/secret/config/supervisord.conf", "rc": 3,
                                   "services": [{"name": "nox-model", "state": "RUNNING", "pid": GPU_PID},
                                                {"name": "nox-worker-stopped", "state": "STOPPED", "pid": None}]}]}
        elif section == "storage":
            result = {"storage_paths": ["/secret/storage/unrelated/path"]}
        row = {"section": section, "worker_pid": 1000 + index, "result": result}
        if section == "process_rows":
            row["bounded_process_identity_inventory"] = _inventory(rows, complete=process_complete)
        sections.append("NOX_MAINT_AUDIT=" + json.dumps(row, separators=(",", ":")))
    return "\n".join(sections + [OP.AUDIT_COMPLETE]) + "\n"


def _replace_section(stdout: str, section: str, edit) -> str:
    lines = stdout.splitlines()
    index = next(i for i, line in enumerate(lines)
                 if line.startswith(OP.AUDIT_PREFIX) and json.loads(line[len(OP.AUDIT_PREFIX):])["section"] == section)
    row = json.loads(lines[index][len(OP.AUDIT_PREFIX):])
    edit(row)
    lines[index] = OP.AUDIT_PREFIX + json.dumps(row, separators=(",", ":"))
    return "\n".join(lines) + "\n"


def _rehash(inventory: dict) -> None:
    inventory["rows_sha256"] = hashlib.sha256(
        json.dumps(inventory["rows"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def transfer_records(marker_line: str):
    return OP.build_transfer_records(marker_line, REQUEST_ID, SOURCE_SHA, force=True)


class OwnerNativeOutputTransferTests(unittest.TestCase):
    def test_8192_process_rows_transfer_as_bounded_digest_checked_minimal_bundle(self):
        stdout = _fixture(8192)
        self.assertGreater(len(stdout.encode("utf-8")), 180_000)
        forwarded = OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)
        records = [line for line in forwarded if line.startswith(OP.TRANSFER_PREFIX)]
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(all(len(line.encode("utf-8")) < OP.MAX_FORWARD_LINE_BYTES for line in forwarded))
        restored = OP.reassemble_transfer_records(records, REQUEST_ID, SOURCE_SHA).decode("utf-8")
        self.assertEqual(restored, OP.audit_bundle_line(stdout))
        self.assertIn("NOX_MAINT_AUDIT_WORKERS_COMPLETE=true", forwarded)
        bundle = json.loads(restored.split("=", 1)[1])
        self.assertEqual(set(bundle) - {"schema", "worker_sections", "redacted_fields", "hardware", "process_rows", "supervisor"}, set())
        inventory = bundle["process_rows"]["bounded_process_identity_inventory"]
        self.assertEqual(len(inventory["rows"]), 8192)
        status = OP.require_audit_census_complete(stdout)
        self.assertTrue(status["process_census_complete"])
        self.assertTrue(status["supervisor_inventory_complete"])
        self.assertTrue(status["supervisor_crosscheck_complete"])
        self.assertTrue(status["gpu_census_complete"])
        self.assertEqual(status["supervisor_command_rc"], 3)
        self.assertIs(status["supervisor_command_success"], False)
        self.assertEqual(status["supervisor_service_health"], "DEGRADED")
        self.assertEqual(status["gpu_pid_reconciliation"][0]["gpu_pid"], GPU_PID)
        self.assertEqual(status["gpu_pid_reconciliation"][0]["classification"], "MATCHED")
        for forbidden in ("SECRET_INLINE_CODE_SHOULD_NOT_FORWARD", "/secret/storage", "/secret/config", "/secret/cgroup"):
            self.assertNotIn(forbidden, restored)
        process_summary = bundle["process_rows"]["filtered_summary"]
        self.assertEqual(process_summary["gpu_consumer_pids"], [GPU_PID])
        self.assertTrue(process_summary["arguments_omitted"])
        self.assertTrue(process_summary["scripts_omitted"])

    def test_complete_marker_cannot_hide_missing_duplicate_or_early_worker_record(self):
        stdout = _fixture(2)
        lines = stdout.splitlines()
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join(lines[:-2] + lines[-1:]))
        duplicate = lines[:]
        duplicate[1] = duplicate[0]
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_SECTION_DUPLICATE|HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join(duplicate))
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_RECORD_SET_INCOMPLETE"):
            OP.audit_bundle_line("\n".join([lines[-1]] + lines[:-1]))

    def test_real_producer_list_shape_inventory_sha_and_secret_sanitization(self):
        stdout = _fixture(2)
        bundle_line = OP.audit_bundle_line(stdout)
        bundle = json.loads(bundle_line.split("=", 1)[1])
        process = bundle["process_rows"]
        self.assertEqual(process["filtered_summary"]["filtered_row_count"], 2)
        self.assertIn("bounded_process_identity_inventory", process)
        inventory = process["bounded_process_identity_inventory"]
        self.assertIn("identity_state", inventory["rows"][0])
        self.assertIn("exe", inventory["rows"][0])
        self.assertNotIn('"arguments":', bundle_line)
        self.assertNotIn('"scripts":', bundle_line)
        self.assertNotIn("/secret", bundle_line)

        changed = _replace_section(stdout, "process_rows", lambda row: row["bounded_process_identity_inventory"].update(rows_sha256="0" * 64))
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_SHA"):
            OP.forward_remote_stdout(changed, "audit", REQUEST_ID, SOURCE_SHA)

    def test_worker_errors_and_missing_result_fail_closed(self):
        stdout = _replace_section(_fixture(2), "storage", lambda row: row.update(error="RuntimeError", result=None))
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_WORKER_INCOMPLETE"):
            OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)

    def test_incomplete_censuses_are_transferred_for_diagnostics_but_audit_holds(self):
        cases = (
            (_fixture(2, process_complete=False), "process_census_complete"),
            (_fixture(2, supervisor_complete=False), "supervisor_inventory_complete"),
            (_fixture(2, gpu_complete=False), "gpu_census_complete"),
            (_fixture(2, gpu_classification="NOT_VISIBLE"), "gpu_census_complete"),
        )
        for stdout, field in cases:
            with self.subTest(gate=field):
                forwarded = OP.forward_remote_stdout(stdout, "audit", REQUEST_ID, SOURCE_SHA)
                self.assertIn("NOX_MAINT_AUDIT_WORKERS_COMPLETE=true", forwarded)
                self.assertFalse(OP.audit_census_status(stdout)[field])
                with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_CENSUS_INCOMPLETE"):
                    OP.require_audit_census_complete(stdout)

    def test_empty_inventory_and_unexpected_inventory_or_row_keys_hold(self):
        def empty(row):
            inv = row["bounded_process_identity_inventory"]
            inv["rows"] = []
            inv["row_count"] = inv["entries_seen"] = 0
            _rehash(inv)
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_SHAPE"):
            OP.audit_bundle_line(_replace_section(_fixture(2), "process_rows", empty))

        def add_cmdline(row):
            inv = row["bounded_process_identity_inventory"]
            inv["rows"][0]["cmdline"] = "SECRET"
            _rehash(inv)
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_ROW_KEYS"):
            OP.audit_bundle_line(_replace_section(_fixture(2), "process_rows", add_cmdline))

        def add_inventory_key(row):
            row["bounded_process_identity_inventory"]["cgroup_paths"] = ["/secret"]
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_KEYS"):
            OP.audit_bundle_line(_replace_section(_fixture(2), "process_rows", add_inventory_key))

        def add_unbounded_missing_field(row):
            inv = row["bounded_process_identity_inventory"]
            inv["rows"][0]["identity_state"] = "IDENTITY_INCOMPLETE"
            inv["rows"][0]["missing_fields"] = ["cmdline"] * 100
            _rehash(inv)
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_MISSING_FIELDS"):
            OP.audit_bundle_line(_replace_section(_fixture(2), "process_rows", add_unbounded_missing_field))

        def add_path_comm(row):
            inv = row["bounded_process_identity_inventory"]
            inv["rows"][0]["comm"] = "/secret/storage/path"
            _rehash(inv)
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_PROCESS_INVENTORY_ROW_VALUE"):
            OP.audit_bundle_line(_replace_section(_fixture(2), "process_rows", add_path_comm))

    def test_gpu_identity_must_join_inventory_and_supervisor_rows(self):
        def drift_join(row):
            link = row["result"]["gpu_process_links"][0]
            link["proc_identity"].update(start_ticks=999999)
            link["service_match"].update(start_ticks=999999)
        changed_identity = _replace_section(_fixture(2), "hardware", drift_join)
        changed_identity = _replace_section(changed_identity, "process_rows", lambda row:
            (row["result"][0].update(start_ticks=999999),
             row["result"][0]["gpu_identity"].update(start_ticks=999999)))
        self.assertFalse(OP.audit_census_status(changed_identity)["gpu_census_complete"])
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_CENSUS_INCOMPLETE"):
            OP.require_audit_census_complete(changed_identity)

        changed_process_gpu = _replace_section(_fixture(2), "process_rows", lambda row:
            row["result"][0]["gpu_identity"].update(start_ticks=999999))
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_FILTERED_GPU_IDENTITY"):
            OP.audit_bundle_line(changed_process_gpu)

        mismatched_supervisor = _replace_section(_fixture(2), "supervisor", lambda row:
            row["result"]["results"][0]["services"][0].update(name="different-service"))
        self.assertFalse(OP.audit_census_status(mismatched_supervisor)["supervisor_crosscheck_complete"])
        with self.assertRaisesRegex(RuntimeError, "HOLD_AUDIT_CENSUS_INCOMPLETE"):
            OP.require_audit_census_complete(mismatched_supervisor)

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
