"""Fail-closed offline fixtures for the bounded owner memory diagnostic."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_memory_diagnostic as diag


class MemoryDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.cgroup = base / "cgroup"
        self.proc = base / "proc"
        self.cgroup.mkdir()
        self.proc.mkdir()
        self.allowlist = diag.DEFAULT_SERVICES
        self.pids = {name: 4000+i for i, name in enumerate(self.allowlist)}
        self.ticks = {pid: 80000+pid for pid in self.pids.values()}
        self.write_cgroup()
        for service, pid in self.pids.items():
            self.add_process(pid, self.ticks[pid])
        self.lease = {
            "schema": diag.LEASE_SCHEMA, "state": diag.LEASE_STATE, "verified": True,
            "lease_kind": "FLOCK", "owner_authorized": True,
            "owner_instance_id": diag.EXPECTED_INSTANCE_ID,
            "holder_pid": self.pids["nox-dispatcher-t855u"],
            "holder_start_ticks": self.ticks[self.pids["nox-dispatcher-t855u"]],
            "supervisor_pid": self.pids["nox-dispatcher-t855u"],
            "supervisor_start_ticks": self.ticks[self.pids["nox-dispatcher-t855u"]],
            "lock_inode": 999, "lock_device_major": 8, "lock_device_minor": 1,
            "owner_config_sha256": "a"*64,
        }
        self.supervisor = "\n".join(
            f"{service} RUNNING pid {self.pids[service]}, uptime 0:10:00"
            for service in self.allowlist
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_cgroup(self, current=100000):
        (self.cgroup / "memory.current").write_text(str(current))
        (self.cgroup / "memory.max").write_text("200000")
        (self.cgroup / "memory.stat").write_text(
            "\n".join(f"{key} {i+1}" for i, key in enumerate(diag.MEMORY_CATEGORIES)) + "\n"
        )

    def add_process(self, pid, ticks, *, rss=10, pss=8, target="/private/secret/model.safetensors"):
        proc = self.proc / str(pid)
        (proc / "fd").mkdir(parents=True, exist_ok=True)
        # /proc stat fields after comm begin at state; starttime is field index 19 here.
        tail = ["S"] + ["0"]*18 + [str(ticks)]
        (proc / "stat").write_text(f"{pid} (fixture process) " + " ".join(tail))
        (proc / "status").write_text(f"Name:\tfixture\nVmRSS:\t{rss} kB\n")
        if pss is not None:
            (proc / "smaps_rollup").write_text(f"Pss:\t{pss} kB\n")
        else:
            (proc / "smaps_rollup").write_text("Rss:\t10 kB\n")
        fd = proc / "fd" / "3"
        if fd.is_symlink() or fd.exists():
            fd.unlink()
        fd.symlink_to(target)
        fd_mem = proc / "fd" / "4"
        if fd_mem.is_symlink() or fd_mem.exists():
            fd_mem.unlink()
        fd_mem.symlink_to("/memfd:private_memfd_secret (deleted)")

    def collect(self, **overrides):
        args = {
            "cgroup_root": self.cgroup, "proc_root": self.proc,
            "supervisor_status": self.supervisor, "supervisor_rc": 0,
            "supervisor_status_after": self.supervisor, "supervisor_rc_after": 0,
            "lease_receipt": self.lease, "lease_observed_at": 100.0,
            "now_unix": 101.0, "service_allowlist": self.allowlist,
        }
        args.update(overrides)
        return diag.collect_owner_memory_diagnostic(**args)

    def test_complete_snapshot_is_diagnostic_only_and_redacts_targets(self):
        result = self.collect()
        self.assertEqual(result["state"], "READ_ONLY_DIAGNOSTIC_COMPLETE")
        self.assertTrue(result["verified"])
        self.assertFalse(result["cleanup_authorized"])
        self.assertFalse(result["mutation_authorized"])
        self.assertEqual(result["safe_to_clear_categories"], [])
        self.assertEqual(result["processes"][0]["rss_bytes"], 10*1024)
        self.assertEqual(result["processes"][0]["pss_bytes"], 8*1024)
        self.assertEqual(len(result["processes"]), len(self.allowlist))
        artifact = result["processes"][0]["artifact_identities"][0]
        self.assertEqual(artifact["kind"], "WEIGHT_OR_CHECKPOINT")
        self.assertRegex(artifact["identity_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["processes"][0]["artifact_identities"][1]["kind"], "MEMFD")
        dumped = json.dumps(result)
        self.assertNotIn("/private/secret", dumped)
        self.assertNotIn("model.safetensors", dumped)
        self.assertNotIn("private_memfd_secret", dumped)
        self.assertNotIn("fixture process", dumped)
        self.assertFalse(any("path" in key.lower() or "content" in key.lower()
                             for row in result["processes"] for key in row))

    def test_missing_pss_fails_closed(self):
        self.add_process(self.pids[self.allowlist[0]], self.ticks[self.pids[self.allowlist[0]]], pss=None)
        self.assertEqual(self.collect()["hold_reason"], "HOLD_MISSING_PSS")

    def test_process_churn_fails_closed(self):
        pid = self.pids[self.allowlist[0]]
        with patch.object(diag, "_read_stat_starttime", side_effect=[self.ticks[pid], self.ticks[pid]+1]):
            self.assertEqual(self.collect()["hold_reason"], "HOLD_PROCESS_CHURN")

    def test_counter_drift_fails_closed(self):
        first = {"current": 100, "max": 200, "categories": {"anon": 1}}
        second = {"current": 101, "max": 200, "categories": {"anon": 1}}
        with patch.object(diag, "_cgroup_snapshot", side_effect=[first, second]):
            self.assertEqual(self.collect()["hold_reason"], "HOLD_COUNTER_DRIFT")

    def test_stale_or_ambiguous_lease_fails_closed(self):
        self.assertEqual(self.collect(lease_observed_at=90.0)["hold_reason"], "HOLD_LEASE_STALE")
        bad = dict(self.lease, holder_pid=1234)
        self.assertEqual(self.collect(lease_receipt=bad)["hold_reason"], "HOLD_LEASE_IDENTITY")
        self.assertEqual(self.collect(lease_receipt={})["hold_reason"], "HOLD_LEASE_UNKNOWN")

    def test_supervisor_churn_fails_closed(self):
        changed = self.supervisor.replace(str(self.pids[self.allowlist[0]]),
                                          "9999", 1)
        self.assertEqual(self.collect(supervisor_status_after=changed)["hold_reason"],
                         "HOLD_SUPERVISOR_CHURN")

    def test_symlink_and_size_bounds_fail_closed(self):
        stat_file = self.cgroup / "memory.stat"
        stat_file.unlink()
        stat_file.symlink_to(self.cgroup / "memory.current")
        self.assertEqual(self.collect()["hold_reason"], "HOLD_UNSAFE_FILE")
        self.write_cgroup()
        pid = self.pids[self.allowlist[0]]
        (self.proc / str(pid) / "smaps_rollup").write_text("Pss: 1 kB\n" + "x"*70000)
        self.assertEqual(self.collect()["hold_reason"], "HOLD_FILE_SIZE_BOUND")

    def test_duplicate_or_missing_memory_category_fails_closed(self):
        (self.cgroup / "memory.stat").write_text("anon 1\nanon 2\n")
        self.assertEqual(self.collect()["hold_reason"], "HOLD_MEMORY_STAT_DUPLICATE")
        self.write_cgroup()
        (self.cgroup / "memory.stat").write_text("anon 1\n")
        self.assertEqual(self.collect()["hold_reason"], "HOLD_MEMORY_CATEGORY_MISSING")


if __name__ == "__main__":
    unittest.main()
