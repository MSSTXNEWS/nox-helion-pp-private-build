"""NOX autonomous research bootstrap for the EXISTING OneHost lifecycle.

No new thread, socket, model, DB or native privilege. Existing owner calls
boot() from startup and tick() from the already-present idle scheduler.
A native S03 policy readback determines whether research can start now.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .growth_sandbox import daily_initiatives
from .worms import WormSwarm, WormHold

MAX_NATIVE_TICK = 4


class WormAutopilot:
    def __init__(self, *, native_signed_policy: Callable, source_head: Callable,
                 swarm: WormSwarm, native_stop: Callable,
                 s03_append_readback: Callable):
        if not isinstance(swarm, WormSwarm) or not all(callable(fn) for fn in
                (native_signed_policy, source_head, native_stop, s03_append_readback)):
            raise WormHold("NOX_WORMS_EXISTING_ONEHOST_CALLBACKS_REQUIRED")
        self._policy = native_signed_policy
        self._source_head = source_head
        self._swarm = swarm
        self._stop = native_stop
        self._persist = s03_append_readback
        self._booted_scope = None
        self._boot_receipt = None

    def _native_stop_status(self):
        """Fail closed if native STOP is unavailable or has an unknown state."""
        try:
            state = self._stop()
        except Exception:
            return "NATIVE_STOP_UNAVAILABLE"
        if state is False:
            return None
        if state is True:
            return "STOPPED_BEFORE_BOOT"
        return "NATIVE_STOP_UNAVAILABLE"

    def boot(self, session, *, now=None):
        """Roles generate original ideas at boot; only approved providers fetch."""
        now = now or datetime.now(timezone.utc)
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise WormHold("NOX_WORMS_BOOT_UTC_REQUIRED")
        head = self._source_head()
        agenda = daily_initiatives(now, source_head=head)
        # Always prepare agenda even without internet / GPU / user account.
        stop_state = self._native_stop_status()
        if stop_state is not None:
            return {**agenda, "state": stop_state, "research_started": False}
        policy = self._policy(session)
        if not isinstance(policy, dict) or policy.get("schema") != "NOX-NATIVE-WORMS-POLICY-v1":
            return {**agenda, "state": "NATIVE_POLICY_NOT_CONFIGURED",
                    "research_started": False}
        if (policy.get("signed_by_native_owner") is not True or
                policy.get("allow_autonomous_public_research") is not True or
                policy.get("approved_source_head") != head or
                policy.get("expires_at_utc") is None):
            return {**agenda, "state": "NATIVE_POLICY_REVIEW_REQUIRED",
                    "research_started": False}
        try:
            expires = datetime.fromisoformat(policy["expires_at_utc"])
        except (TypeError, ValueError):
            return {**agenda, "state": "NATIVE_POLICY_EXPIRY_INVALID",
                    "research_started": False}
        if expires.tzinfo is None or expires.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
            return {**agenda, "state": "NATIVE_POLICY_EXPIRED",
                    "research_started": False}
        if self._booted_scope is not None and self._booted_scope != session:
            return {**agenda, "state": "NATIVE_SCOPE_CHANGED",
                    "research_started": False}
        # STOP/head/policy may be revoked before the durable S03 append.
        if self._native_stop_status() is not None or self._source_head() != head:
            return {**agenda, "state": "NATIVE_STOP_OR_HEAD_CHANGED_BEFORE_S03",
                    "research_started": False}
        if self._policy(session) != policy:
            return {**agenda, "state": "NATIVE_POLICY_CHANGED_BEFORE_S03",
                    "research_started": False}
        # The existing native owner S03 thread records the one boot agenda.
        if self._boot_receipt is None:
            if self._persist(session, agenda) is not True:
                return {**agenda, "state": "S03_BOOT_READBACK_REQUIRED",
                        "research_started": False}
            self._boot_receipt = agenda
            self._booted_scope = session
        # STOP, source HEAD or policy may change during native S03 write.
        stop_state = self._native_stop_status()
        if stop_state is not None:
            return {**agenda, "state": stop_state, "research_started": False}
        if self._source_head() != head:
            return {**agenda, "state": "NATIVE_STOP_OR_HEAD_CHANGED_AFTER_S03",
                    "research_started": False}
        if self._policy(session) != policy:
            return {**agenda, "state": "NATIVE_POLICY_CHANGED_AFTER_S03",
                    "research_started": False}
        # WormSwarm.set_enabled independently re-checks native ACL + consent.
        try:
            self._swarm.set_enabled(session, True)
        except WormHold:
            return {**agenda, "state": "NATIVE_WORM_RESEARCH_AUTH_HOLD",
                    "research_started": False}
        return {**agenda, "state": "RESEARCH_READY_FOR_EXISTING_IDLE_TICK",
                "research_started": False}

    def tick(self, session, *, now=None):
        """Called by the EXISTING OneHost idle loop; no hidden activity."""
        stop_state = self._native_stop_status()
        if stop_state is not None or self._booted_scope != session:
            return {**self._swarm.status(), "reason": (
                "STOP_OR_SCOPE_HOLD" if stop_state in (None, "STOPPED_BEFORE_BOOT")
                else stop_state)}
        policy = self._policy(session)
        now = now or datetime.now(timezone.utc)
        if not isinstance(policy, dict) or policy.get("schema") != "NOX-NATIVE-WORMS-POLICY-v1":
            return {**self._swarm.status(), "reason": "NATIVE_POLICY_REVOKED"}
        if (policy.get("signed_by_native_owner") is not True or
                policy.get("allow_autonomous_public_research") is not True or
                policy.get("approved_source_head") != self._source_head()):
            return {**self._swarm.status(), "reason": "NATIVE_POLICY_REVOKED"}
        try:
            expires = datetime.fromisoformat(policy["expires_at_utc"])
        except (TypeError, ValueError, KeyError):
            return {**self._swarm.status(), "reason": "NATIVE_POLICY_EXPIRED"}
        if expires.tzinfo is None or expires.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
            return {**self._swarm.status(), "reason": "NATIVE_POLICY_EXPIRED"}
        stop_state = self._native_stop_status()
        if stop_state is not None:
            return {**self._swarm.status(), "reason": stop_state}
        return self._swarm.tick(session, now=now, max_tasks=MAX_NATIVE_TICK)

    def stop(self, session):
        return self._swarm.set_enabled(session, False)

    def status(self):
        return {"schema": "NOX-WORMS-AUTOPILOT-v1",
                "boot_agenda_saved": self._boot_receipt is not None,
                "native_runtime_wired": False,  # I0 OneHost binding must prove
                **self._swarm.status()}
