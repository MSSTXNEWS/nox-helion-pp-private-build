"""Tool-use priority scheduler for the NOX mind v4.1 staging layer.

Stdlib only. This is not the OneHost dispatcher and it does not start threads
or processes. The caller drives execution so tests stay deterministic.

Selection order, lowest key first:
1. effective priority class (SAFETY, then USER_FACING, then BACKGROUND)
2. submission sequence (FIFO inside a class)
3. call id, as a total tie-break

Aging: after each ``aging_quantum`` of wait, a non-safety call moves one class
upward, and stops at USER_FACING. An aged background call therefore runs before
a newer user-facing call, and it never runs before SAFETY.

Deadlines are start-by instants on the injected clock. A queued call with
``now > deadline`` becomes EXPIRED and is not executed. A timeout is a run
budget measured from ``started_at``. When the clock passes it, the in-flight
slot is released and a late result is discarded. The scheduler cannot kill a
running callable; timeout is cooperative with the clock.

Cancellation of a queued call marks it CANCELLED. Cancellation of a running
call sets a flag the callable can observe and turn into ``Cancelled``.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional


class Priority(IntEnum):
    SAFETY = 0
    USER_FACING = 1
    BACKGROUND = 2


class Status:
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class Cancelled(Exception):
    """Raised by a callable that observed a cancellation request."""


@dataclass
class ToolCall:
    call_id: str
    tool: str
    fn: Callable[..., Any]
    args: tuple
    kwargs: dict
    priority: Priority
    enqueued_at: float
    sequence: int
    deadline: Optional[float] = None
    timeout: Optional[float] = None
    status: str = Status.QUEUED
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_requested: bool = False
    effective_class: int = field(default=0, compare=False)


class ToolScheduler:
    def __init__(self, concurrency: int = 1, aging_quantum: float = 10.0, clock: Callable[[], float] | None = None):
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if aging_quantum < 0:
            raise ValueError("aging_quantum must be >= 0")
        self.concurrency = concurrency
        self.aging_quantum = aging_quantum
        self.clock = clock or time.monotonic
        self._seq = itertools.count()
        self._calls: dict[str, ToolCall] = {}
        self._running: list[str] = []

    def submit(
        self,
        tool: str,
        fn: Callable[..., Any],
        *,
        args: tuple = (),
        kwargs: dict | None = None,
        priority: Priority | str | int = Priority.USER_FACING,
        deadline: float | None = None,
        timeout: float | None = None,
        call_id: str | None = None,
        now: float | None = None,
    ) -> str:
        if not callable(fn):
            raise TypeError("fn must be callable")
        priority = _coerce_priority(priority)
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be >= 0")
        now = self.clock() if now is None else now
        sequence = next(self._seq)
        if call_id is None:
            call_id = f"c{sequence}"
        if call_id in self._calls:
            raise ValueError(f"duplicate call_id {call_id}")
        self._calls[call_id] = ToolCall(
            call_id=call_id,
            tool=tool,
            fn=fn,
            args=tuple(args),
            kwargs=dict(kwargs or {}),
            priority=priority,
            enqueued_at=now,
            sequence=sequence,
            deadline=deadline,
            timeout=timeout,
        )
        return call_id

    def get(self, call_id: str) -> ToolCall:
        return self._calls[call_id]

    def effective_class(self, call: ToolCall, now: float) -> int:
        base = int(call.priority)
        if base <= int(Priority.SAFETY) or self.aging_quantum <= 0:
            return base
        steps = int(max(0.0, now - call.enqueued_at) // self.aging_quantum)
        return max(int(Priority.USER_FACING), base - steps)

    def ordered(self, now: float | None = None) -> list[ToolCall]:
        """Queued calls in selection order. Does not expire or start anything."""
        now = self.clock() if now is None else now
        queued = [c for c in self._calls.values() if c.status == Status.QUEUED]
        for c in queued:
            c.effective_class = self.effective_class(c, now)
        queued.sort(key=lambda c: (c.effective_class, c.sequence, c.call_id))
        return queued

    def cancel(self, call_id: str, now: float | None = None) -> bool:
        call = self._calls[call_id]
        now = self.clock() if now is None else now
        if call.status == Status.QUEUED:
            call.status = Status.CANCELLED
            call.finished_at = now
            call.cancel_requested = True
            return True
        if call.status == Status.RUNNING:
            call.cancel_requested = True
            return True
        return False

    def cancellation_requested(self, call_id: str) -> bool:
        return self._calls[call_id].cancel_requested

    def sweep(self, now: float | None = None) -> list[str]:
        """Expire missed deadlines and time out in-flight calls. Returns changed ids."""
        now = self.clock() if now is None else now
        changed: list[str] = []
        for call in self._calls.values():
            if call.status == Status.QUEUED and call.deadline is not None and now > call.deadline:
                call.status = Status.EXPIRED
                call.finished_at = now
                changed.append(call.call_id)
        for call_id in list(self._running):
            call = self._calls[call_id]
            if call.timeout is not None and call.started_at is not None and now > call.started_at + call.timeout:
                call.status = Status.TIMED_OUT
                call.finished_at = now
                call.result = None
                self._running.remove(call_id)
                changed.append(call_id)
        return changed

    def pop_next(self, now: float | None = None) -> ToolCall | None:
        """Mark the next eligible call RUNNING, or return None when blocked or idle."""
        now = self.clock() if now is None else now
        self.sweep(now)
        if len(self._running) >= self.concurrency:
            return None
        queued = self.ordered(now)
        if not queued:
            return None
        call = queued[0]
        call.status = Status.RUNNING
        call.started_at = now
        self._running.append(call.call_id)
        return call

    def complete(self, call_id: str, result: Any, now: float | None = None) -> ToolCall:
        call = self._require_running(call_id)
        now = self.clock() if now is None else now
        if call.timeout is not None and call.started_at is not None and now > call.started_at + call.timeout:
            call.status = Status.TIMED_OUT
            call.finished_at = now
            call.result = None
            self._release(call_id)
            return call
        call.status = Status.DONE
        call.result = result
        call.finished_at = now
        self._release(call_id)
        return call

    def fail(self, call_id: str, exc: BaseException, now: float | None = None) -> ToolCall:
        call = self._require_running(call_id)
        now = self.clock() if now is None else now
        call.status = Status.FAILED
        call.error = f"{type(exc).__name__}: {exc}"
        call.finished_at = now
        self._release(call_id)
        return call

    def finish_cancelled(self, call_id: str, now: float | None = None) -> ToolCall:
        call = self._require_running(call_id)
        now = self.clock() if now is None else now
        call.status = Status.CANCELLED
        call.finished_at = now
        call.cancel_requested = True
        self._release(call_id)
        return call

    def execute_next(self, now: float | None = None) -> ToolCall | None:
        """Pop one call and run it on this thread. Ordering stays the pop order."""
        now = self.clock() if now is None else now
        call = self.pop_next(now)
        if call is None:
            return None
        if call.cancel_requested:
            return self.finish_cancelled(call.call_id, now)
        try:
            result = call.fn(*call.args, **call.kwargs)
        except Cancelled:
            return self.finish_cancelled(call.call_id, self.clock())
        except Exception as exc:
            return self.fail(call.call_id, exc, self.clock())
        return self.complete(call.call_id, result, self.clock())

    def _require_running(self, call_id: str) -> ToolCall:
        call = self._calls[call_id]
        if call.status != Status.RUNNING or call_id not in self._running:
            raise ValueError(f"{call_id} is {call.status}, not running")
        return call

    def _release(self, call_id: str) -> None:
        if call_id in self._running:
            self._running.remove(call_id)


def _coerce_priority(priority: Priority | str | int) -> Priority:
    if isinstance(priority, Priority):
        return priority
    if isinstance(priority, str):
        return Priority[priority.strip().upper()]
    return Priority(priority)
