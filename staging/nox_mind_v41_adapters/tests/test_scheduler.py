"""Deterministic tests for the staging tool-use priority scheduler."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "staging"))

from nox_mind_v41_adapters.scheduler import Cancelled, Priority, Status, ToolScheduler


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def _ids(calls):
    return [call.call_id for call in calls]


class TestScheduler(unittest.TestCase):
    def test_priority_and_fifo_are_deterministic(self):
        clock = Clock(0)
        sched = ToolScheduler(concurrency=1, aging_quantum=10, clock=clock)
        sched.submit("background", lambda: "b", priority="BACKGROUND", call_id="bg", now=0)
        sched.submit("user", lambda: "u", priority=Priority.USER_FACING, call_id="user", now=0)
        sched.submit("safety", lambda: "s", priority=Priority.SAFETY, call_id="safe", now=0)
        sched.submit("user-later", lambda: "u2", priority=Priority.USER_FACING, call_id="user-2", now=0)
        self.assertEqual(_ids(sched.ordered(0)), ["safe", "user", "user-2", "bg"])
        first = sched.execute_next(now=0)
        second = sched.execute_next(now=0)
        self.assertEqual([first.call_id, second.call_id], ["safe", "user"])
        self.assertEqual(first.result, "s")
        self.assertEqual(first.status, Status.DONE)
        again = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))
        for name, priority, cid in (
            ("background", Priority.BACKGROUND, "bg"),
            ("user", Priority.USER_FACING, "user"),
            ("safety", Priority.SAFETY, "safe"),
            ("user-later", Priority.USER_FACING, "user-2"),
        ):
            again.submit(name, lambda: None, priority=priority, call_id=cid, now=0)
        self.assertEqual(_ids(again.ordered(0)), ["safe", "user", "user-2", "bg"])

    def test_aging_avoids_starvation_without_passing_safety(self):
        sched = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))
        sched.submit("background", lambda: "b", priority=Priority.BACKGROUND, call_id="bg", now=0)
        sched.submit("user", lambda: "u", priority=Priority.USER_FACING, call_id="user", now=5)
        sched.submit("safety", lambda: "s", priority=Priority.SAFETY, call_id="safe", now=5)
        self.assertEqual(_ids(sched.ordered(5)), ["safe", "user", "bg"])
        self.assertEqual(_ids(sched.ordered(10)), ["safe", "bg", "user"])
        self.assertEqual(_ids(sched.ordered(10_000)), ["safe", "bg", "user"])
        self.assertEqual(sched.pop_next(now=10).call_id, "safe")
        self.assertEqual(sched.pop_next(now=10), None)
        sched.complete("safe", "s", now=10)
        self.assertEqual(sched.pop_next(now=10).call_id, "bg")

    def test_deadline_expires_before_start(self):
        sched = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))
        sched.submit("late", lambda: "no", priority=Priority.USER_FACING, call_id="late", deadline=5, now=0)
        sched.submit("ok", lambda: "yes", priority=Priority.USER_FACING, call_id="ok", now=0)
        chosen = sched.execute_next(now=6)
        self.assertEqual(chosen.call_id, "ok")
        self.assertEqual(chosen.result, "yes")
        self.assertEqual(sched.get("late").status, Status.EXPIRED)
        self.assertIsNone(sched.get("late").result)

    def test_timeout_releases_slot_and_discards_late_result(self):
        clock = Clock(0)
        sched = ToolScheduler(concurrency=1, aging_quantum=10, clock=clock)

        def slow():
            clock.t = 100
            return "late"

        sched.submit("slow", slow, priority=Priority.USER_FACING, call_id="slow", timeout=5, now=0)
        finished = sched.execute_next(now=0)
        self.assertEqual(finished.status, Status.TIMED_OUT)
        self.assertIsNone(finished.result)
        sched.submit("next", lambda: "ok", call_id="next", now=100)
        nxt = sched.execute_next(now=100)
        self.assertEqual(nxt.call_id, "next")
        self.assertEqual(nxt.status, Status.DONE)

        parked = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))
        parked.submit("held", lambda: "x", call_id="held", timeout=5, now=0)
        self.assertEqual(parked.pop_next(now=0).call_id, "held")
        self.assertEqual(parked.sweep(now=6), ["held"])
        self.assertEqual(parked.get("held").status, Status.TIMED_OUT)
        with self.assertRaises(ValueError):
            parked.complete("held", "x", now=6)
        parked.submit("after", lambda: "y", call_id="after", now=6)
        self.assertEqual(parked.pop_next(now=6).call_id, "after")

    def test_cancel_queued_and_running(self):
        sched = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))
        sched.submit("drop", lambda: "no", call_id="drop", now=0)
        sched.submit("keep", lambda: "yes", call_id="keep", now=0)
        self.assertTrue(sched.cancel("drop", now=1))
        self.assertEqual(sched.get("drop").status, Status.CANCELLED)
        self.assertFalse(sched.cancel("drop", now=1))
        self.assertEqual(sched.execute_next(now=1).call_id, "keep")

        coop = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))

        def worker():
            coop.cancel("run", now=2)
            if coop.cancellation_requested("run"):
                raise Cancelled()
            return "should-not"

        coop.submit("run", worker, call_id="run", now=0)
        done = coop.execute_next(now=0)
        self.assertEqual(done.status, Status.CANCELLED)
        self.assertIsNone(done.result)

    def test_concurrency_limit_and_failure_frees_slot(self):
        sched = ToolScheduler(concurrency=2, aging_quantum=10, clock=Clock(0))
        for cid, priority in (("safe", Priority.SAFETY), ("user", Priority.USER_FACING), ("bg", Priority.BACKGROUND)):
            sched.submit(cid, lambda: cid, priority=priority, call_id=cid, now=0)
        first = sched.pop_next(now=0)
        second = sched.pop_next(now=0)
        self.assertIsNone(sched.pop_next(now=0))
        self.assertEqual([first.call_id, second.call_id], ["safe", "user"])
        sched.complete("safe", "ok", now=1)
        self.assertEqual(sched.pop_next(now=1).call_id, "bg")

        failing = ToolScheduler(concurrency=1, aging_quantum=10, clock=Clock(0))

        def boom():
            raise RuntimeError("tool failed")

        failing.submit("bad", boom, call_id="bad", now=0)
        failed = failing.execute_next(now=0)
        self.assertEqual(failed.status, Status.FAILED)
        self.assertIn("tool failed", failed.error)
        failing.submit("after", lambda: "recovered", call_id="after", now=1)
        self.assertEqual(failing.execute_next(now=1).result, "recovered")

    def test_rejects_bad_arguments(self):
        with self.assertRaises(ValueError):
            ToolScheduler(concurrency=0)
        sched = ToolScheduler(clock=Clock(0))
        sched.submit("once", lambda: None, call_id="once", now=0)
        with self.assertRaises(ValueError):
            sched.submit("twice", lambda: None, call_id="once", now=0)
        with self.assertRaises(TypeError):
            sched.submit("nope", None, now=0)


if __name__ == "__main__":
    unittest.main()
