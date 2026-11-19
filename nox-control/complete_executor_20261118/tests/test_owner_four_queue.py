"""Exact source unit tests, not proof of native deployment or real worker PIDs."""
import unittest

from owner_autonomy_pool import (
    AutoHold, QUEUE_IDS, SCHEMA, admit_native_tick, choose_ready,
    tick_existing_dispatcher, validate_submission,
)
from test_owner_normal3_continuity import Native


def task(queue, n, **changes):
    return {"id": "q%d-%d" % (queue + 1, n), "queue_id": QUEUE_IDS[queue],
            "handler": "reviewed_cpu", "deps": [], "priority": "P2",
            "resource": "CPU_LIGHT", "source_sha256": "b" * 64,
            "estimated_cost": 1, "title": "reviewed task", **changes}


def select(tasks, status=None, **kw):
    return choose_ready(tasks, status=status or {}, mode=kw.pop("mode", "NORMAL"),
                        memory_ratio=.1, **kw)


class ClaimingNative(Native):
    """An in-memory callback contract fixture; no server operation is simulated as real."""
    def __init__(self, tasks):
        super().__init__(count=3)
        self.tasks = tasks
        self.status = {}
        self.claimed = []

    def read_reviewed_catalog(self): return {"schema": SCHEMA, "tasks": self.tasks}
    def allowed_handlers(self): return {"reviewed_cpu"}
    def read_resource_snapshot(self):
        latest = next((row for row in self.tasks if self.claimed and row['id'] == self.claimed[-1]), None)
        return {"native_verified": True, "instance_id": 60509551,
                "stop_active": False, "source_sha_verified": True,
                "owner_scope_verified": True, "task_status": self.status.copy(),
                "cgroup_memory_ratio": .1, "cpu_pressure": 0,
                "gpu_available": False,
                "queue_cursor": (QUEUE_IDS.index(latest['queue_id']) + 1) % 4 if latest else 0}
    def native_duplicate_check(self, task_id): return task_id in self.status
    def native_queue_claim(self, item, owner_pids):
        self.status[item["id"]] = "pending"
        self.claimed.append(item["id"])
        return {"job_id": "job-" + item["id"]}
    def s03_readback(self, task_id, job_id):
        return {"native_verified": True, "task_id": task_id,
                "job_id": job_id, "receipt_sha256": "a" * 64}


class FourQueueTests(unittest.TestCase):
    def test_reviewed_schema_accepts_exact_four_queues(self):
        catalog = {"schema": SCHEMA, "tasks": [task(i, 0) for i in range(4)]}
        result = validate_submission(catalog, allowed_handlers={"reviewed_cpu"})
        self.assertEqual({r["queue_id"] for r in result["ordered"]}, set(QUEUE_IDS))
        catalog["tasks"][0]["queue_id"] = "unreviewed"
        with self.assertRaisesRegex(AutoHold, "HOLD_TASK_QUEUE_ID"):
            validate_submission(catalog, allowed_handlers={"reviewed_cpu"})

    def test_four_queues_three_global_slots_and_no_starvation(self):
        tasks = [task(q, n) for q in range(4) for n in range(4)]
        status = {}
        seen = []
        for _ in range(6):
            ready = select(tasks, status)
            self.assertLessEqual(len(ready), 3)
            seen.extend(r["queue_id"] for r in ready)
            status.update({r["id"]: "done" for r in ready})
        self.assertEqual(len(seen), 16)
        for start in range(0, 16, 4):
            self.assertEqual(seen[start:start + 4], list(QUEUE_IDS))

    def test_pending_and_running_share_one_cap(self):
        tasks = [task(q, n) for q in range(4) for n in range(2)]
        status = {"q1-0": "pending", "q2-0": "running"}
        self.assertEqual([r["queue_id"] for r in select(tasks, status)], [QUEUE_IDS[2]])
        status["q3-0"] = "pending"
        self.assertEqual(select(tasks, status), [])

    def test_failed_and_pending_claims_advance_fourth_queue_turn(self):
        tasks = [task(q, n) for q in range(4) for n in range(2)]
        status = {"q1-0": "failed", "q2-0": "pending", "q3-0": "done"}
        self.assertEqual(select(tasks, status)[0]["queue_id"], QUEUE_IDS[3])

    def test_unknown_and_null_claims_reserve_slots_without_replay(self):
        tasks = [task(q, n) for q in range(4) for n in range(2)]
        status = {"q1-0": None, "q2-0": {"state": "ACK_LOST"}}
        self.assertEqual([r["id"] for r in select(tasks, status)], ["q3-0"])
        status["q3-0"] = "blocked"
        self.assertEqual(select(tasks, status), [])

    def test_only_successful_native_terminals_release_dependency(self):
        tasks = [task(0, 0, deps=["gate"])]
        self.assertEqual(len(select(tasks, {"gate": "COMPLETED"})), 1)
        self.assertEqual(select(tasks, {"gate": "FAILED"}), [])

    def test_empty_and_dependency_blocked_queues_donate_capacity(self):
        tasks = [task(0, 0, deps=["gate"])] + [task(2, n) for n in range(5)]
        ready = select(tasks)
        self.assertEqual(len(ready), 3)
        self.assertEqual({r["queue_id"] for r in ready}, {QUEUE_IDS[2]})

    def test_skipped_empty_queue_serves_each_remaining_queue_once(self):
        tasks = [task(q, n) for q in (1, 2, 3) for n in range(2)]
        self.assertEqual([r['queue_id'] for r in select(tasks, queue_cursor=0)], list(QUEUE_IDS[1:]))
        status = {'q2-0': 'done'}
        self.assertEqual(select(tasks, status, queue_cursor=2)[0]['queue_id'], QUEUE_IDS[2])

    def test_priority_is_preserved_within_each_queue(self):
        tasks = [task(q, 0, priority="P3") for q in range(4)]
        tasks += [task(0, 1, priority="P0")]
        self.assertEqual([r["id"] for r in select(tasks)], ["q1-1", "q2-0", "q3-0"])

    def test_unmapped_mixed_catalog_is_explicit_hold(self):
        tasks = [task(0, 0), task(1, 0)]
        tasks[1].pop("queue_id")
        with self.assertRaisesRegex(AutoHold, "HOLD_MIXED_OR_UNKNOWN_QUEUES"):
            select(tasks)

    def test_boost_cannot_exceed_owner_default_three(self):
        tasks = [task(q, n) for q in range(4) for n in range(3)]
        self.assertEqual(len(select(tasks, mode="FORSAZH")), 3)
        self.assertEqual(len(select(tasks, mode="FORSAZH", worker_cap=2)), 2)

    def test_existing_tick_and_claim_callbacks_reuse_three_workers(self):
        native = ClaimingNative([task(q, n) for q in range(4) for n in range(2)])
        namespace = {"_nox_owner_autonomy_native": native}
        first = tick_existing_dispatcher(namespace, {}, mode="FORSAZH")
        self.assertEqual(first["jobs_started"], 3)
        self.assertEqual(native.claimed, ["q1-0", "q2-0", "q3-0"])
        pending = tick_existing_dispatcher(namespace, {}, mode="NORMAL")
        self.assertEqual(pending["state"], "NATIVE_POOL_CONTINUING")
        self.assertEqual(pending["jobs_started"], 0)
        native.status.update({key: "done" for key in native.status})
        second = tick_existing_dispatcher(namespace, {}, mode="NORMAL")
        self.assertEqual(second["jobs_started"], 3)
        self.assertEqual(native.claimed[3:], ["q4-0", "q1-1", "q2-1"])
        self.assertEqual(native.ensure_calls, 0)

    def test_stop_and_resource_pressure_still_prevent_admission(self):
        native = ClaimingNative([task(q, 0) for q in range(4)])
        native.stop = True
        result = admit_native_tick(native, tasks=native.tasks, status={},
                                   mode="FORSAZH", memory_ratio=.1)
        self.assertEqual(result["state"], "HOLD_OWNER_STOP_OR_WRITER_LEASE")
        native.stop = False
        result = admit_native_tick(native, tasks=native.tasks, status={},
                                   mode="FORSAZH", memory_ratio=.96)
        self.assertEqual(result["state"], "HOLD_RESOURCE_PRESSURE")
        self.assertEqual(native.claimed, [])


if __name__ == "__main__":
    unittest.main()
