"""Synthetic tests for fail-closed V100/RAM/KV budget admission; no GPU access."""
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


def fixture(now=None):
    now = now or datetime.now(timezone.utc)
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
    return observation, budget, now


class MayaRuntimeMemoryBudgetTests(unittest.TestCase):
    def test_fresh_balanced_v100_and_cgroup_budget_is_source_only(self):
        observation, budget, now = fixture()
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "SOURCE_ONLY_MEMORY_BUDGET_FIT_NOT_RUNTIME_VERIFIED")
        self.assertFalse(got["launchable"])
        self.assertFalse(got["measured"])
        self.assertFalse(got["telemetry_authenticated"])
        self.assertEqual(got["gpu_headroom_bytes"], {"0": 7 * 1024 ** 3, "1": 7 * 1024 ** 3})
        self.assertEqual(got["cgroup_free_bytes"], 32 * 1024 ** 3)

    def test_asymmetric_gpu_free_memory_holds_on_the_limiting_device(self):
        observation, budget, now = fixture()
        observation["gpus"][1]["free_bytes"] = 16 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "HOLD_RUNTIME_GPU_MEMORY_BUDGET")
        self.assertEqual(got["gpu_id"], 1)
        self.assertEqual(got["deficit_bytes"], 1 * 1024 ** 3)

    def test_reserve_is_included_in_each_gpu_budget(self):
        observation, budget, now = fixture()
        observation["gpus"][0]["free_bytes"] = 16 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "HOLD_RUNTIME_GPU_MEMORY_BUDGET")
        self.assertEqual(got["gpu_id"], 0)
        self.assertEqual(got["required_bytes"], 17 * 1024 ** 3)

    def test_expired_gpu_sample_is_hold(self):
        observation, budget, now = fixture()
        stale = (now - timedelta(seconds=11)).isoformat()
        observation["gpus"][0]["captured_at"] = stale
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "HOLD_RUNTIME_GPU_TELEMETRY_STALE")

    def test_expired_cgroup_sample_is_hold(self):
        observation, budget, now = fixture()
        observation["cgroup"]["captured_at"] = (now - timedelta(seconds=11)).isoformat()
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "HOLD_RUNTIME_CGROUP_TELEMETRY_STALE")

    def test_missing_static_or_malformed_telemetry_is_hold(self):
        observation, budget, now = fixture()
        observation["gpus"][0].pop("captured_at")
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)["state"],
                         "HOLD_RUNTIME_GPU_TELEMETRY_STALE")
        observation, budget, now = fixture()
        observation["gpus"][0]["source"] = "static"
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)["state"],
                         "HOLD_RUNTIME_GPU_SOURCE")
        observation, budget, now = fixture()
        observation["gpus"][0]["free_bytes"] = True
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)["state"],
                         "HOLD_RUNTIME_GPU_MEMORY_READING")

    def test_cgroup_ram_reserve_is_included(self):
        observation, budget, now = fixture()
        observation["cgroup"]["current_bytes"] = 40 * 1024 ** 3
        got = BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)
        self.assertEqual(got["state"], "HOLD_RUNTIME_CGROUP_MEMORY_BUDGET")
        self.assertEqual(got["deficit_bytes"], 5 * 1024 ** 3)

    def test_invalid_gpu_identity_and_context_budget_hold(self):
        observation, budget, now = fixture()
        observation["gpus"][1]["name"] = "NVIDIA RTX 4090"
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)["state"],
                         "HOLD_RUNTIME_GPU_IDENTITY")
        observation, budget, now = fixture()
        budget["context_tokens"] = 65536
        self.assertEqual(BUDGET.evaluate_memory_budget(observation, budget, now_utc=now)["state"],
                         "HOLD_RUNTIME_BUDGET_CONTEXT")


if __name__ == "__main__":
    unittest.main()
