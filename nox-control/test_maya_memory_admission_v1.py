"""Synthetic resource-boundary tests; never reads host/GPU telemetry."""
from __future__ import annotations

import unittest

import maya_memory_admission_v1 as memory

NOW = 1_800_000_000.0
GIB = 1024 ** 3


def snapshot():
    return {
        "status": "LIVE_READBACK",
        "source": "native_live_readback",
        "measured": True,
        "captured_at": NOW,
        "gpus": [
            {"gpu_id": 0, "name": "Tesla V100", "total_bytes": 16 * GIB, "free_bytes": 9 * GIB},
            {"gpu_id": 1, "name": "Tesla V100", "total_bytes": 15 * GIB, "free_bytes": 8 * GIB},
        ],
        "cgroup": {
            "source": "cgroup_v2",
            "limit_bytes": 64 * GIB,
            "current_bytes": 16 * GIB,
            "free_bytes": 48 * GIB,
        },
    }


def budget():
    return {
        "source": "verified_pack_budget",
        "pack_sha256": "a" * 64,
        "context_tokens": 4096,
        "parallel_requests": 1,
        "per_gpu": [
            {"gpu_id": 0, "model_resident_bytes": 1 * GIB, "activation_bytes": 1 * GIB,
             "kv_cache_bytes": 1 * GIB, "reserve_bytes": 3 * GIB},
            {"gpu_id": 1, "model_resident_bytes": 1 * GIB, "activation_bytes": 1 * GIB,
             "kv_cache_bytes": 1 * GIB, "reserve_bytes": 3 * GIB},
        ],
        "host": {"model_resident_bytes": 8 * GIB, "activation_bytes": 2 * GIB,
                 "kv_cache_bytes": 4 * GIB, "reserve_bytes": 4 * GIB},
    }


def evaluate(snap=None, plan=None, **kwargs):
    return memory.evaluate_memory_admission(
        snapshot=snapshot() if snap is None else snap,
        budget=budget() if plan is None else plan,
        now_seconds=NOW,
        **kwargs,
    )


class MayaMemoryAdmissionTests(unittest.TestCase):
    def test_fresh_two_v100_asymmetric_snapshot_passes_per_gpu_and_never_launches(self):
        got = evaluate()
        self.assertEqual(got["state"], "MEMORY_ADMISSION_PASS_SOURCE_ONLY")
        self.assertFalse(got["launchable"])
        self.assertEqual([x["total_bytes"] for x in got["per_gpu"]], [16 * GIB, 15 * GIB])
        self.assertEqual([x["gpu_id"] for x in got["per_gpu"]], [0, 1])

    def test_asymmetric_free_vram_holds_on_the_smaller_gpu_even_if_pair_sum_fits(self):
        snap = snapshot()
        snap["gpus"][1]["free_bytes"] = 5 * GIB
        got = evaluate(snap=snap)
        self.assertEqual(got["state"], "HOLD_MEMORY_VRAM_BUDGET_EXCEEDS_FREE")
        self.assertEqual(got["gpu_id"], 1)
        self.assertFalse(got["launchable"])

    def test_gpu_reserve_shortfall_holds(self):
        plan = budget()
        plan["per_gpu"][1]["reserve_bytes"] = 2 * GIB
        got = evaluate(plan=plan)
        self.assertEqual(got["state"], "HOLD_MEMORY_GPU_RESERVE_TOO_SMALL")
        self.assertEqual(got["gpu_id"], 1)

    def test_stale_telemetry_holds(self):
        snap = snapshot()
        snap["captured_at"] = NOW - 16
        self.assertEqual(evaluate(snap=snap)["state"], "HOLD_MEMORY_TELEMETRY_STALE")

    def test_static_snapshot_holds(self):
        snap = snapshot()
        snap["source"] = "static_profile"
        snap["measured"] = False
        self.assertEqual(evaluate(snap=snap)["state"], "HOLD_MEMORY_STATIC_OR_UNVERIFIED_SNAPSHOT")

    def test_missing_per_gpu_or_cgroup_free_memory_holds(self):
        snap = snapshot()
        snap["gpus"].pop()
        self.assertEqual(evaluate(snap=snap)["state"], "HOLD_MEMORY_TWO_GPU_READBACK_REQUIRED")
        snap = snapshot()
        del snap["cgroup"]["free_bytes"]
        self.assertEqual(evaluate(snap=snap)["state"], "HOLD_MEMORY_CGROUP_READBACK_MALFORMED")

    def test_cgroup_host_budget_overflow_holds(self):
        plan = budget()
        plan["host"]["model_resident_bytes"] = 44 * GIB
        got = evaluate(plan=plan)
        self.assertEqual(got["state"], "HOLD_MEMORY_RAM_BUDGET_EXCEEDS_FREE")
        self.assertFalse(got["launchable"])

    def test_context_budget_mismatch_holds(self):
        plan = budget()
        plan["context_tokens"] = 8192
        self.assertEqual(evaluate(plan=plan)["state"], "HOLD_MEMORY_CONTEXT_OR_PARALLEL_BUDGET_MISMATCH")

    def test_unpinned_or_missing_budget_holds(self):
        plan = budget()
        plan["pack_sha256"] = "unknown"
        self.assertEqual(evaluate(plan=plan)["state"], "HOLD_MEMORY_MODEL_BUDGET_UNPINNED")
        self.assertEqual(memory.evaluate_memory_admission(snapshot=snapshot(), budget=None,
                                                          now_seconds=NOW)["state"],
                         "HOLD_MEMORY_VERIFIED_MODEL_BUDGET_REQUIRED")


if __name__ == "__main__":
    unittest.main()
