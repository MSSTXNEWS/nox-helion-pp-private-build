"""Synthetic tests for estimate-only V100/RAM/KV admission; no GPU access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "maya_runtime_memory_budget_v1",
    Path(__file__).with_name("maya_runtime_memory_budget_v1.py"),
)
BUDGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUDGET)


def fixture():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    gib = 1024 ** 3
    observation = {
        "readback_id": "fixture-owner-native-001",
        "gpus": [
            {"id": 0, "name": BUDGET.GPU_NAME, "total_bytes": 32 * gib,
             "free_bytes": 24 * gib, "captured_at": stamp, "source": "nvidia-smi"},
            {"id": 1, "name": BUDGET.GPU_NAME, "total_bytes": 32 * gib,
             "free_bytes": 24 * gib, "captured_at": stamp, "source": "nvidia-smi"},
        ],
        "cgroup": {"current_bytes": 16 * gib, "max_bytes": 48 * gib,
                   "captured_at": stamp, "source": "cgroup-v2"},
    }
    budget = {
        "gpu_ids": [0, 1],
        "context_tokens": 4096,
        "model_resident_bytes_by_gpu": [4 * gib, 4 * gib],
        "activation_bytes_by_gpu": [2 * gib, 2 * gib],
        "kv_cache_bytes_by_gpu": [8 * gib, 8 * gib],
        "gpu_reserve_bytes_by_gpu": [3 * gib, 3 * gib],
        "host_model_resident_bytes": 8 * gib,
        "host_activation_bytes": 1 * gib,
        "host_kv_cache_bytes": 0,
        "host_reserve_bytes": 4 * gib,
    }
    return observation, budget


class MayaRuntimeMemoryBudgetTests(unittest.TestCase):
    def test_fresh_reading_is_estimate_only_and_never_admission(self):
        observation, budget = fixture()
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertFalse(got["admission"])
        self.assertFalse(got["launchable"])
        self.assertTrue(got["estimate_only"])
        self.assertFalse(got["telemetry_authenticated"])
        self.assertFalse(got["provenance_verified"])
        self.assertEqual(got["arithmetic_state"], "WITHIN_REPORTED_CAPACITY")
        self.assertEqual(
            {key: row["estimated_headroom_bytes"] for key, row in got["estimated_gpu_budget"].items()},
            {"0": 7 * 1024 ** 3, "1": 7 * 1024 ** 3},
        )
        self.assertEqual(got["estimated_cgroup_free_bytes"], 32 * 1024 ** 3)

    def test_forged_tiny_budget_and_zero_activations_still_cannot_admit(self):
        observation, budget = fixture()
        # Fresh timestamps, nvidia-smi labels, a nonempty readback ID, and
        # undersized caller allocations are deliberately forgeable input.
        observation["readback_id"] = "forged-static-row"
        budget["model_resident_bytes_by_gpu"] = [1, 1]
        budget["activation_bytes_by_gpu"] = [0, 0]
        budget["kv_cache_bytes_by_gpu"] = [1, 1]
        budget["gpu_reserve_bytes_by_gpu"] = [1, 1]
        budget["host_model_resident_bytes"] = 1
        budget["host_activation_bytes"] = 0
        budget["host_kv_cache_bytes"] = 0
        budget["host_reserve_bytes"] = 1
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["arithmetic_state"], "WITHIN_REPORTED_CAPACITY")
        self.assertFalse(got["admission"])
        self.assertFalse(got["telemetry_authenticated"])
        self.assertFalse(got["provenance_verified"])

    def test_asymmetric_gpu_free_memory_is_reported_as_estimate_only_hold(self):
        observation, budget = fixture()
        observation["gpus"][1]["free_bytes"] = 16 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["arithmetic_state"], "OVERCOMMITTED")
        self.assertEqual(got["arithmetic_overcommit"]["resource"], "gpu")
        self.assertEqual(got["arithmetic_overcommit"]["gpu_id"], 1)
        self.assertEqual(got["arithmetic_overcommit"]["deficit_bytes"], 1 * 1024 ** 3)
        self.assertFalse(got["admission"])

    def test_gpu_reserve_is_included_in_arithmetic_estimate(self):
        observation, budget = fixture()
        observation["gpus"][0]["free_bytes"] = 16 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget)
        row = got["estimated_gpu_budget"]["0"]
        self.assertEqual(row["estimated_required_bytes"], 17 * 1024 ** 3)
        self.assertEqual(row["estimated_headroom_bytes"], -1 * 1024 ** 3)
        self.assertEqual(got["arithmetic_overcommit"]["gpu_id"], 0)
        self.assertFalse(got["admission"])

    def test_expired_gpu_sample_holds(self):
        observation, budget = fixture()
        observation["gpus"][0]["captured_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=11)
        ).isoformat()
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_RUNTIME_GPU_TELEMETRY_STALE")
        self.assertEqual(got["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertFalse(got["admission"])

    def test_expired_cgroup_sample_holds(self):
        observation, budget = fixture()
        observation["cgroup"]["captured_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=11)
        ).isoformat()
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_RUNTIME_CGROUP_TELEMETRY_STALE")
        self.assertFalse(got["admission"])

    def test_stale_sample_cannot_be_refreshed_with_forged_now_utc(self):
        observation, budget = fixture()
        old = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
        observation["gpus"][0]["captured_at"] = old
        observation["now_utc"] = old
        budget["now_utc"] = old
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_RUNTIME_GPU_TELEMETRY_STALE")
        with self.assertRaises(TypeError):
            BUDGET.evaluate_memory_budget(observation, budget, now_utc=old)

    def test_static_source_and_malformed_readings_hold(self):
        observation, budget = fixture()
        observation["gpus"][0].pop("captured_at")
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget)["state"],
                         "HOLD_RUNTIME_GPU_TELEMETRY_STALE")
        observation, budget = fixture()
        observation["gpus"][0]["source"] = "static"
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget)["state"],
                         "HOLD_RUNTIME_GPU_SOURCE")
        observation, budget = fixture()
        observation["gpus"][0]["free_bytes"] = True
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget)["state"],
                         "HOLD_RUNTIME_GPU_MEMORY_READING")

    def test_cgroup_reserve_is_included_in_arithmetic_estimate(self):
        observation, budget = fixture()
        observation["cgroup"]["current_bytes"] = 40 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget)
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["arithmetic_state"], "OVERCOMMITTED")
        self.assertEqual(got["arithmetic_overcommit"]["resource"], "cgroup")
        self.assertEqual(got["arithmetic_overcommit"]["deficit_bytes"], 5 * 1024 ** 3)
        self.assertFalse(got["admission"])

    def test_invalid_gpu_identity_and_context_budget_hold(self):
        observation, budget = fixture()
        observation["gpus"][1]["name"] = "NVIDIA RTX 4090"
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget)["state"],
                         "HOLD_RUNTIME_GPU_IDENTITY")
        observation, budget = fixture()
        budget["context_tokens"] = 65536
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget)["state"],
                         "HOLD_RUNTIME_BUDGET_CONTEXT")


if __name__ == "__main__":
    unittest.main()
