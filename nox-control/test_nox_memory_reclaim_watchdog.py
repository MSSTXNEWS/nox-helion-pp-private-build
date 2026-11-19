"""Memory reclaim watchdog safety tests; all cgroups and files are temporary."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nox_memory_reclaim_watchdog as guard


MIB = guard.MIB
GIB = guard.GIB


def base_policy(**updates):
    value = {
        "schema": guard.POLICY_SCHEMA,
        "enabled": False,
        "target_unit": "",
        "expected_control_group": "",
        "high_watermark_fraction": 0.85,
        "low_watermark_fraction": 0.80,
        "max_reclaim_bytes": 128 * MIB,
        "minimum_reclaim_bytes": 16 * MIB,
        "daily_budget_bytes": 512 * MIB,
        "cooldown_seconds": 900,
        "poll_seconds": 60,
    }
    value.update(updates)
    return guard.validate_policy(value)


def sample(current=950 * MIB, *, high=0, oom=0, oom_kill=0,
           shmem=100 * MIB, file_mapped=100 * MIB, inactive=500 * MIB):
    return {
        "sampled_at_unix": 10,
        "sample_duration_ns": 1,
        "memory_current_bytes": current,
        "memory_max_bytes": GIB,
        "memory_high_bytes": None,
        "memory_stat": {
            "anon": 200 * MIB, "file": 800 * MIB, "shmem": shmem,
            "inactive_file": inactive, "active_file": 100 * MIB,
            "file_mapped": file_mapped, "file_dirty": 10 * MIB,
            "file_writeback": 10 * MIB,
        },
        "clean_inactive_file_estimate_bytes": guard.clean_file_estimate({
            "file": 800 * MIB, "shmem": shmem, "inactive_file": inactive,
            "file_mapped": file_mapped, "file_dirty": 10 * MIB,
            "file_writeback": 10 * MIB,
        }),
        "events": {"high": high, "oom": oom, "oom_kill": oom_kill},
        "psi_avg10": {"some": 0.0, "full": 0.0},
    }


class MemoryReclaimWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.leaf = self.root / "system.slice" / "nox-cache.service"
        self.leaf.mkdir(parents=True)
        self.leaf_id = (1, 2, 0)
        self.cg = self.root / "cgroup"
        self.cg.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def policy(self, **updates):
        return base_policy(enabled=True, target_unit="nox-cache.service",
                           expected_control_group="/system.slice/nox-cache.service", **updates)

    def test_disabled_policy_has_no_cgroup_or_systemd_side_effect(self):
        with patch.object(guard, "resolve_target", side_effect=AssertionError("must not resolve")):
            result = guard.run_cycle(base_policy(), self.state, source_sha="a" * 64,
                                     policy_sha="b" * 64, now=1000)
        self.assertEqual(result["action"], "NONE")
        self.assertTrue((self.state / "state.json").is_file())

    def test_root_cgroup_and_unapproved_unit_are_rejected(self):
        with self.assertRaisesRegex(guard.Hold, "CONTROL_GROUP"):
            guard.safe_control_group("/", "nox-cache.service")
        with self.assertRaisesRegex(guard.Hold, "UNIT_ALLOWLIST"):
            guard.safe_control_group("/system.slice/ssh.service", "ssh.service")
        with self.assertRaisesRegex(guard.Hold, "CONTROL_GROUP_UNIT_MISMATCH"):
            guard.safe_control_group("/system.slice/nox-other.service", "nox-cache.service")

    def test_policy_is_disabled_until_exact_service_leaf_is_pinned(self):
        self.assertFalse(base_policy()["enabled"])
        with self.assertRaisesRegex(guard.Hold, "DISABLED_POLICY_TARGET"):
            base_policy(target_unit="nox-cache.service")
        with self.assertRaisesRegex(guard.Hold, "POLICY_WATERMARKS"):
            base_policy(high_watermark_fraction=0.75, low_watermark_fraction=0.80)
        with self.assertRaisesRegex(guard.Hold, "POLICY_RECLAIM_BUDGET"):
            base_policy(max_reclaim_bytes=256 * MIB, daily_budget_bytes=128 * MIB)

    def test_clean_cache_estimate_excludes_shmem_mapped_dirty_and_writeback(self):
        stats = {"file": 800 * MIB, "shmem": 250 * MIB,
                 "inactive_file": 700 * MIB, "file_mapped": 300 * MIB,
                 "file_dirty": 50 * MIB, "file_writeback": 25 * MIB}
        self.assertEqual(guard.clean_file_estimate(stats), 175 * MIB)
        stats["shmem"] = 800 * MIB
        self.assertEqual(guard.clean_file_estimate(stats), 0)

    def test_leaf_resolution_requires_systemd_mapping_memory_reclaim_and_no_children(self):
        for name, content in (("cgroup.type", "domain\n"), ("cgroup.procs", "101\n"),
                              ("memory.reclaim", "")):
            (self.leaf / name).write_text(content)
        self.leaf.chmod(0o755)
        with patch.object(guard, "_systemctl", side_effect=["", "/system.slice/nox-cache.service"]):
            fd, identity = guard.resolve_target("nox-cache.service", "/system.slice/nox-cache.service",
                                                self.root)
            os.close(fd)
        self.assertEqual(identity[2], os.geteuid())
        (self.leaf / "child.slice").mkdir()
        with patch.object(guard, "_systemctl", side_effect=["", "/system.slice/nox-cache.service"]):
            with self.assertRaisesRegex(guard.Hold, "NOT_A_LEAF"):
                guard.resolve_target("nox-cache.service", "/system.slice/nox-cache.service", self.root)

    def test_missing_reclaim_interface_fails_closed(self):
        (self.leaf / "cgroup.type").write_text("domain\n")
        with patch.object(guard, "_systemctl", side_effect=["", "/system.slice/nox-cache.service"]):
            with self.assertRaisesRegex(guard.Hold, "INTERFACE_MISSING"):
                guard.resolve_target("nox-cache.service", "/system.slice/nox-cache.service", self.root)

    def test_sample_uses_fresh_cgroup_data_and_rejects_missing_shmem_metrics(self):
        values = {
            "memory.current": "900\n", "memory.max": "1000\n", "memory.high": "max\n",
            "memory.stat": "file 800\nshmem 250\ninactive_file 700\nfile_mapped 300\nfile_dirty 50\nfile_writeback 25\nanon 100\nactive_file 10\n",
            "memory.events": "high 0\noom 0\noom_kill 0\n",
            "memory.pressure": "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
        }
        for name, value in values.items():
            (self.cg / name).write_text(value)
        fd = os.open(self.cg, os.O_RDONLY | os.O_DIRECTORY)
        try:
            observed = guard.sample_cgroup(fd, 123)
        finally:
            os.close(fd)
        self.assertEqual(observed["sampled_at_unix"], 123)
        self.assertEqual(observed["clean_inactive_file_estimate_bytes"], 175)
        (self.cg / "memory.stat").write_text("file 10\ninactive_file 10\n")
        fd = os.open(self.cg, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaisesRegex(guard.Hold, "MEMORY_STAT_REQUIRED"):
                guard.sample_cgroup(fd)
        finally:
            os.close(fd)

    def _run(self, policy, *, now, samples, state_setup=None, writer_calls=None,
             stop_check=lambda: False, writer=None):
        if state_setup:
            state_setup()
        sample_calls = iter(samples)
        calls = writer_calls if writer_calls is not None else []

        def resolve(_unit, _group, _root):
            return os.open(self.leaf, os.O_RDONLY | os.O_DIRECTORY), self.leaf_id

        def member(_fd, _proc_root):
            return [(101, 901)], "member-fingerprint"

        def take_sample(_fd):
            return next(sample_calls)

        def write_reclaim(_fd, amount):
            calls.append(amount)

        with patch.object(guard, "_target_path_identity", return_value=self.leaf_id):
            with patch.object(guard, "_systemctl", side_effect=["", "/system.slice/nox-cache.service"]):
                result = guard.run_cycle(policy, self.state, cgroup_root=self.root,
                    source_sha="a" * 64, policy_sha="b" * 64, now=now,
                    resolve=resolve, sample=take_sample, member=member,
                    writer=writer or write_reclaim, stop_check=stop_check)
        return result, calls

    def test_reclaim_requires_durable_baseline_then_requests_bounded_clean_cache(self):
        policy = self.policy()
        baseline, _ = self._run(policy, now=1000, samples=[sample()])
        self.assertEqual(baseline["kind"], "BASELINE")
        before = sample()
        after = sample(current=850 * MIB)
        result, calls = self._run(policy, now=2000, samples=[before, before, after])
        self.assertEqual(result["kind"], "RECLAIM_ATTEMPT")
        self.assertEqual(result["action"], "MEMORY_RECLAIM_SWAPPINESS_0")
        self.assertEqual(len(calls), 1)
        self.assertLessEqual(calls[0], policy["max_reclaim_bytes"])
        self.assertEqual(calls[0] % 4096, 0)
        saved = json.loads((self.state / "state.json").read_text())
        self.assertIsNone(saved["pending"])
        self.assertEqual(saved["latest"]["source_sha256"], "a" * 64)
        self.assertIn("KERNEL_MAY_OVER_OR_UNDER_RECLAIM", saved["latest"]["kernel_result_scope"])

    def test_below_threshold_cooldown_and_pending_intent_do_not_reclaim(self):
        policy = self.policy()
        self._run(policy, now=1000, samples=[sample(current=700 * MIB)])
        result, calls = self._run(policy, now=2000, samples=[sample(current=700 * MIB)])
        self.assertEqual(result["action"], "BELOW_THRESHOLD")
        self.assertEqual(calls, [])

        state = json.loads((self.state / "state.json").read_text())
        state["pending"] = {"request_id": "uncertain"}
        guard._write_state(self.state, state)
        result, calls = self._run(policy, now=3000, samples=[])
        self.assertEqual(result["code"], "HOLD_MEMORY_RECLAIM_UNRESOLVED_ACTION")
        self.assertEqual(calls, [])

    def test_cooldown_and_daily_budget_gate_high_memory(self):
        policy = self.policy()
        self._run(policy, now=1000, samples=[sample()])
        first, calls = self._run(policy, now=2000,
                                 samples=[sample(), sample(), sample(current=850 * MIB)])
        self.assertEqual(first["kind"], "RECLAIM_ATTEMPT")
        cooldown, calls = self._run(policy, now=2500, samples=[sample()])
        self.assertEqual(cooldown["action"], "COOLDOWN")
        self.assertEqual(calls, [])

        state = json.loads((self.state / "state.json").read_text())
        state["last_action_unix"] = 1000
        state["daily_requests"] = [[2499, policy["daily_budget_bytes"]]]
        guard._write_state(self.state, state)
        limited, calls = self._run(policy, now=4000, samples=[sample()])
        self.assertEqual(limited["action"], "HOLD_NO_SAFE_CLEAN_CACHE")
        self.assertEqual(calls, [])

    def test_ambiguous_reclaim_write_keeps_durable_pending_intent(self):
        policy = self.policy()
        self._run(policy, now=1000, samples=[sample()])

        def uncertain(_fd, _amount):
            raise OSError(5, "synthetic uncertain cgroupfs write")

        result, calls = self._run(policy, now=2000, samples=[sample(), sample()],
                                  stop_check=lambda: False, writer=uncertain)
        self.assertEqual(result["code"], "HOLD_MEMORY_RECLAIM_WRITE_AMBIGUOUS")
        saved = json.loads((self.state / "state.json").read_text())
        self.assertEqual(saved["pending"]["request_id"], result["request_id"])
        self.assertEqual(saved["latest"]["kind"], "HOLD")

    def test_policy_schema_and_source_have_no_global_purge(self):
        with self.assertRaisesRegex(guard.Hold, "POLICY_SCHEMA"):
            guard.validate_policy({})
        source = Path(guard.__file__).read_text()
        self.assertNotIn("drop_caches", source)
        self.assertNotIn("/proc/sys/vm", source)

    def test_bad_finite_memory_limit_format_is_rejected(self):
        values = {
            "memory.current": "900\n", "memory.max": "max\n", "memory.high": "max\n",
            "memory.stat": "file 800\nshmem 250\ninactive_file 700\nfile_mapped 300\nfile_dirty 50\nfile_writeback 25\nanon 100\nactive_file 10\n",
            "memory.events": "high 0\noom 0\noom_kill 0\n",
            "memory.pressure": "some avg10=0.00\nfull avg10=0.00\n",
        }
        for name, value in values.items():
            (self.cg / name).write_text(value)
        fd = os.open(self.cg, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaisesRegex(guard.Hold, "LIMIT_FORMAT"):
                guard.sample_cgroup(fd)
        finally:
            os.close(fd)

    def test_recent_oom_blocks_reclaim(self):
        policy = self.policy()
        self._run(policy, now=1000, samples=[sample()])
        result, calls = self._run(policy, now=2000, samples=[sample(oom_kill=1)])
        self.assertEqual(result["code"], "HOLD_MEMORY_RECLAIM_RECENT_OOM")
        self.assertEqual(calls, [])

    def test_stop_marker_blocks_reclaim_and_receipt_is_durable(self):
        policy = self.policy()
        result, calls = self._run(policy, now=1000, samples=[],
            stop_check=lambda: True)
        self.assertEqual(result["kind"], "HOLD")
        self.assertEqual(result["code"], "HOLD_MEMORY_RECLAIM_STOP_MARKER")
        self.assertEqual(calls, [])
        self.assertTrue((self.state / "state.json").is_file())


if __name__ == "__main__":
    unittest.main()
