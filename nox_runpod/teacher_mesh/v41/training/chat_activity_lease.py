"""Chat-first lease for the EXISTING NOX OneHost, not a new scheduler/service.

The existing authenticated proxy calls begin once before returning streaming
content and end only AFTER the stream terminates (or STOP/error disconnect).
A returned StreamingResponse is NOT proof the answer finished. Unknown state
fails closed: idle training cannot take chat VRAM while a lease is active.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from time import monotonic
import re

_REQUEST = re.compile(r"^[a-zA-Z0-9._:-]{4,120}$")


@dataclass(frozen=True)
class LeaseSnapshot:
    chat_state: str
    seconds_since_chat_activity: float
    active_streams: int
    source: str = "EXISTING_ONEHOST_CHAT_PROXY"


class ChatActivityLease:
    def __init__(self, grace_seconds: float = 45.0, clock=monotonic):
        if not 0 <= grace_seconds <= 600:
            raise ValueError("INVALID_GRACE")
        self._clock = clock
        self._grace = grace_seconds
        self._lock = RLock()
        self._running = set()
        self._last = clock()
        self._has_heartbeat = False

    def begin(self, request_id: str) -> bool:
        if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
            raise ValueError("INVALID_REQUEST_ID")
        with self._lock:
            first = request_id not in self._running
            self._running.add(request_id)
            self._last = self._clock()
            self._has_heartbeat = True
            return first

    def heartbeat(self, request_id: str) -> None:
        with self._lock:
            if request_id not in self._running:
                raise ValueError("NO_ACTIVE_LEASE")
            self._last = self._clock()

    def end(self, request_id: str) -> bool:
        with self._lock:
            existed = request_id in self._running
            if existed:
                self._running.remove(request_id)
                self._last = self._clock()
            return existed

    def snapshot(self) -> LeaseSnapshot | None:
        with self._lock:
            if not self._has_heartbeat:
                return None  # fail closed if the existing proxy has not wired activity
            elapsed = max(0.0, self._clock() - self._last)
            active = len(self._running)
            return LeaseSnapshot("generating" if active else "idle",elapsed,active)

    def should_pause_background(self) -> bool:
        snap = self.snapshot()
        return snap is None or snap.active_streams > 0 or snap.seconds_since_chat_activity < self._grace

    def __enter__(self):
        raise RuntimeError("Use per-request begin/end; never a global anonymous lease")
