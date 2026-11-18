"""Native callback simulation for NORMAL3 continuity and fenced replacement.

These tests do NOT launch actual server workers. Run:
    python -m unittest -v test_owner_normal3_continuity.py
"""
import unittest
from owner_autonomy_pool import admit_native_tick


def worker(n):
    return {"pid": 2000 + n, "process_starttime": 12340 + n,
            "instance_id": 60509551, "origin": "existing_onehost",
            "native_pid_verified": True, "state": "RUNNING"}


class Native:
    def __init__(self, count=3, stop=False, lease=True, reconciled=True):
        self.count, self.stop, self.lease = count, stop, lease
        self.reconciled = reconciled
        self.ensure_calls = 0
        self.reconcile_calls = 0

    def owner_allowed(self): return True
    def stop_active(self): return self.stop
    def writer_lease(self): return self.lease
    def ensure_processes(self, n):
        self.ensure_calls += 1
        self.count = n
        return True
    def process_readback(self): return [worker(i) for i in range(self.count)]
    def native_duplicate_check(self, *args): return False
    def native_queue_claim(self, *args, **kw): return {"job_id": "unused"}
    def s03_readback(self, *args): return {}
    def reconcile_worker_claims(self):
        self.reconcile_calls += 1
        return self.reconciled


def tick(native, status, **kw):
    return admit_native_tick(native, tasks=[], status=status,
                             mode="NORMAL", memory_ratio=kw.get("memory_ratio", .1),
                             cpu_pressure=kw.get("cpu_pressure", 0))


class NormalThreeContinuity(unittest.TestCase):
    def test_three_running_without_new_ready_are_preserved(self):
        native = Native(count=3)
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "NATIVE_POOL_CONTINUING")
        self.assertEqual(result["active_subexecutor_processes"], 3)
        self.assertEqual(native.ensure_calls, 0)

    def test_one_missing_worker_requires_fenced_reconcile_then_replenish(self):
        native = Native(count=2)
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "NATIVE_POOL_CONTINUING")
        self.assertEqual(native.reconcile_calls, 1)
        self.assertEqual(native.ensure_calls, 1)
        self.assertEqual(result["active_subexecutor_processes"], 3)

    def test_unreconciled_claim_never_restarts_worker(self):
        native = Native(count=2, reconciled=False)
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED")
        self.assertEqual(native.ensure_calls, 0)

    def test_missing_reconciler_never_restarts_worker(self):
        native = Native(count=2)
        native.reconcile_worker_claims = None
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED")
        self.assertEqual(native.ensure_calls, 0)

    def test_no_ready_no_running_does_not_spawn_fake_workers(self):
        native = Native(count=0)
        result = tick(native, {"finished": "done"})
        self.assertEqual(result["state"], "NATIVE_QUEUE_IDLE")
        self.assertEqual(native.ensure_calls, 0)

    def test_stop_blocks_all_native_work(self):
        native = Native(count=2, stop=True)
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "HOLD_OWNER_STOP_OR_WRITER_LEASE")
        self.assertEqual(native.ensure_calls, 0)

    def test_missing_lease_blocks_all_native_work(self):
        native = Native(count=2, lease=False)
        result = tick(native, {"existing": "running"})
        self.assertEqual(result["state"], "HOLD_OWNER_STOP_OR_WRITER_LEASE")
        self.assertEqual(native.ensure_calls, 0)

    def test_critical_memory_pressure_never_spawns(self):
        native = Native(count=2)
        result = tick(native, {"existing": "running"}, memory_ratio=.96)
        self.assertEqual(result["state"], "HOLD_RESOURCE_PRESSURE")
        self.assertEqual(native.ensure_calls, 0)

    def test_cpu_pressure_does_not_shrink_active_three_to_one(self):
        native = Native(count=3)
        result = tick(native, {"existing": "running"}, cpu_pressure=55)
        self.assertEqual(result["state"], "HOLD_POOL_ABOVE_ADMITTED_TARGET")
        self.assertEqual(native.ensure_calls, 0)
        self.assertEqual(native.reconcile_calls, 0)

    def test_ready_task_reuses_existing_three_without_relaunch(self):
        class ClaimingNative(Native):
            def native_queue_claim(self, task, **kw):
                self.claimed = task["id"]
                return {"job_id": "job-1"}
            def s03_readback(self, task_id, job_id):
                return {"native_verified": True, "task_id": task_id,
                        "job_id": job_id, "receipt_sha256": "a" * 64}

        native = ClaimingNative(count=3)
        task = {"id":"1A01","deps":[],"priority":"P0",
                "resource":"CPU_LIGHT","handler":"reviewed_cpu",
                "source_sha256":"b"*64,"estimated_cost":1}
        result=admit_native_tick(native,tasks=[task],status={},
                                 mode="NORMAL",memory_ratio=.1)
        self.assertEqual(result["state"],"NATIVE_QUEUE_READBACK_VERIFIED")
        self.assertEqual(result["jobs_started"],1)
        self.assertEqual(native.claimed,"1A01")
        self.assertEqual(native.ensure_calls,0)


if __name__ == "__main__":
    unittest.main()
