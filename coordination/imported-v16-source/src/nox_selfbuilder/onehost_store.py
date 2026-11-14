"""PATCH02: serialize the ORIGINAL Store on its owning SQLite thread.

The host provides one trusted factory opening the EXISTING S03/helion.sqlite3.
No second database, migration, writer, background socket or shared connection.
Never expose a raw sqlite3 connection or cursor across threads.
"""
from __future__ import annotations
from concurrent.futures import Future, TimeoutError
from queue import Queue, Full
from threading import Thread, get_ident, Lock
from typing import Callable, Any
import sqlite3


class StoreActorHold(RuntimeError):
    pass


_SIMPLE = (type(None), bool, int, float, str, bytes)


def _detach(value: Any, depth: int = 0):
    """Return immutable, materialized results; never leak a thread-affine cursor."""
    if depth > 10:
        raise StoreActorHold("STORE_RESULT_NESTING_HOLD")
    if isinstance(value, (sqlite3.Connection, sqlite3.Cursor)):
        raise StoreActorHold("STORE_RAW_CONNECTION_CURSOR_DENIED")
    if type(value) in _SIMPLE:
        return value
    if type(value) in (list, tuple):
        return tuple(_detach(x, depth + 1) for x in value)
    if type(value) is dict and len(value) <= 5000:
        if any(type(k) is not str for k in value):
            raise StoreActorHold("STORE_RESULT_KEYS_HOLD")
        return {k: _detach(v, depth + 1) for k, v in value.items()}
    raise StoreActorHold("STORE_RESULT_NOT_TRANSFERABLE")


class OneHostStoreActor:
    """Call ONLY authenticated native-owned closures; never accept functions from JS.

    The factory is executed *inside* the owner's worker thread, and must open
    the original application database; callers must not create Store first.
    Close joins the worker and closes its original resource on that thread.
    """
    is_original_store_actor = True

    def __init__(self, native_store_factory: Callable[[], object], *, max_queue=32):
        if not callable(native_store_factory) or type(max_queue) is not int or not 1 <= max_queue <= 128:
            raise ValueError("TRUSTED_STORE_FACTORY_AND_BOUNDED_QUEUE_REQUIRED")
        self._q = Queue(maxsize=max_queue)
        self._closed = False
        self._lifecycle = Lock()
        self._thread_id = None
        self._start = Future()
        self._thread = Thread(target=self._loop, args=(native_store_factory,),
                              name="NOX-existing-S03-owner", daemon=True)
        self._thread.start()
        self._start.result(timeout=15)

    def _loop(self, factory):
        self._thread_id = get_ident()
        obj = None
        try:
            obj = factory()
            if obj is None:
                raise StoreActorHold("EXISTING_STORE_FACTORY_UNAVAILABLE")
            self._start.set_result(True)
            while True:
                task = self._q.get()
                if task is None:
                    return
                action, result = task
                if not result.set_running_or_notify_cancel():
                    continue
                try:
                    result.set_result(_detach(action(obj)))
                except BaseException as exc:
                    result.set_exception(exc)
        except BaseException as exc:
            if not self._start.done():
                self._start.set_exception(exc)
        finally:
            if obj is not None:
                closer = getattr(obj, "close", None)
                if callable(closer):
                    closer()
                else:
                    conn = getattr(obj, "conn", None)
                    if isinstance(conn, sqlite3.Connection):
                        conn.close()

    def call(self, trusted_native_action: Callable[[object], Any], *, timeout=30):
        if not callable(trusted_native_action) or type(timeout) not in (int, float) or not 0 < timeout <= 600:
            raise ValueError("BOUNDED_NATIVE_STORE_ACTION_REQUIRED")
        if get_ident() == self._thread_id:
            raise StoreActorHold("REENTRANT_STORE_ACTOR_CALL_DENIED")
        result = Future()
        with self._lifecycle:
            if self._closed or not self._thread.is_alive():
                raise StoreActorHold("ORIGINAL_STORE_ACTOR_CLOSED")
            try:
                self._q.put((trusted_native_action, result), timeout=min(timeout, 1))
            except Full as exc:
                raise StoreActorHold("EXISTING_S03_OWNER_BUSY") from exc
        try:
            return result.result(timeout=timeout)
        except TimeoutError as exc:
            if result.done():
                raise
            # Never execute a queued mutation after its caller timed out. An
            # already running native transaction must finish/rollback itself;
            # report that distinction so callers do not blindly retry a write.
            cancelled = result.cancel()
            raise StoreActorHold("STORE_CALL_TIMEOUT_CANCELLED" if cancelled else
                                 "STORE_CALL_TIMEOUT_OUTCOME_UNKNOWN") from exc

    def close(self, *, timeout=15):
        if type(timeout) not in (int, float) or not 0 < timeout <= 600:
            raise ValueError("BOUNDED_STORE_CLOSE_REQUIRED")
        if get_ident() == self._thread_id:
            raise StoreActorHold("REENTRANT_STORE_ACTOR_CLOSE_DENIED")
        with self._lifecycle:
            if not self._closed:
                # Serialize sentinel admission with task admission. Otherwise a
                # close/call race could strand a Future behind the sentinel.
                try:
                    self._q.put(None, timeout=timeout)
                except Full as exc:
                    raise StoreActorHold("ORIGINAL_STORE_DRAIN_TIMEOUT") from exc
                self._closed = True
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise StoreActorHold("ORIGINAL_STORE_DRAIN_TIMEOUT")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
