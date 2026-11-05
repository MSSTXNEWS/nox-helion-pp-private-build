"""E06-only fail-closed semantic gate for the existing events.v3 publisher.

No event bus, worker, host, HTTP listener, or synthetic native receipt is created.
The caller must still verify the canonical envelope and actual owner evidence.
"""
from __future__ import annotations


class EventStateHold(ValueError):
    """The native event type and its claimed state contradict each other."""


_TERMINAL_PAIRS = {
    "task.completed": "COMPLETED",
    "task.failed": "ERROR",
    "model.stopped": "STOPPED",
}
_NONTERMINAL_TYPES = frozenset((
    "task.started", "task.progress", "model.tokens", "training.step", "gpu.sample",
))
_TERMINAL_STATES = frozenset(("COMPLETED", "STOPPED", "READY"))


def require_event_state_coherence(event_type: object, state: object) -> None:
    """Reject contradictory evidence before the real native owner is consulted.

    This gate is a necessary condition, never a substitute for a signed/native
    evidence receipt or the existing SourceLock and event-publish checks.
    """
    if type(event_type) is not str or type(state) is not str:
        raise EventStateHold("EVENT_STATE_REQUIRES_EXACT_STRINGS")
    expected = _TERMINAL_PAIRS.get(event_type)
    if expected is not None and state != expected:
        raise EventStateHold("EVENT_TERMINAL_TYPE_STATE_MISMATCH")
    if event_type in _NONTERMINAL_TYPES and state in _TERMINAL_STATES:
        raise EventStateHold("EVENT_NONTERMINAL_CLAIMS_ACCEPTANCE")
