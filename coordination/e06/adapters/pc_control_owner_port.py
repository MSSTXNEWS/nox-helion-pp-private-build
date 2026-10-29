"""Source-only PACK01 port for the original E11 PC preview/STOP interface.

The authenticated host supplies an EXISTING session-owned E11Service binding.
This adapter creates no backend, state store, permission, or process. E11's
privileged pc_enable_readonly/pc_execute_preview APIs remain host-only; this
route exposes neither. NoxPackHost retains dangerous-action native consent.
"""
from dataclasses import dataclass
from helion.e11.service import E11Service, scope_id
from native_bridge import BoundPort, HostDenied, HostHold, NativeSession, NoxPackHost, _native_owner_scope

ROUTE = "system.pc_control"


@dataclass(frozen=True)
class NativePcBinding:
    """Trusted host result, never page JSON; service belongs to this session.

    pc_stop revokes every preview in the original service instance. A resolver
    must therefore return an already-owned session service, not a shared
    multi-principal service. No service is allocated by this adapter.
    """
    session: NativeSession
    service: E11Service
    project_id: str


def _scope(session):
    if type(session) is not NativeSession:
        raise HostDenied("Native PC session required")
    session.validate()
    if ROUTE not in session.allowed or ROUTE not in session.private_approved:
        raise HostDenied("Native PC scope required")
    # Within NoxPackHost.execute, this also probes the pinned live Windows
    # SID/session lease at each original E11 preview/STOP owner boundary.
    return _native_owner_scope(session)


class ExistingPcControlPort:
    def __init__(self, *, native_binding_from_session, owner_ready):
        if not callable(native_binding_from_session) or not callable(owner_ready):
            raise HostHold("Existing authenticated PC binding and readiness required")
        self._binding = native_binding_from_session
        self._ready = owner_ready

    def execute(self, session, payload):
        before = _scope(session)
        if type(payload) is not dict:
            raise HostDenied("PC preview/STOP object required")
        op = payload.get("op")
        if op == "stop":
            if set(payload) != {"op"}:
                raise HostDenied("STOP takes no page identity or permission")
            command = {"op": "stop"}
        elif op == "preview":
            if set(payload) not in ({"op", "action"}, {"op", "action", "filename"}):
                raise HostDenied("PC preview cannot supply host scope or consent")
            action = payload["action"]
            if type(action) is not str or action not in (
                    "read-system-summary", "inventory-local-exports", "verify-local-export"):
                raise HostDenied("Original PC preview action required")
            command = {"op": "preview", "action": action}
            if "filename" in payload:
                if type(payload["filename"]) is not str or len(payload["filename"]) > 100:
                    raise HostDenied("Bounded original export filename required")
                command["filename"] = payload["filename"]
        else:
            raise HostDenied("Only original PC preview and STOP are page routes")
        try:
            binding = self._binding(session)
        except Exception as exc:
            raise HostHold("Authenticated existing PC binding unavailable") from exc
        if _scope(session) != before:
            raise HostDenied("Native PC scope changed during binding")
        if (type(binding) is not NativePcBinding or binding.session is not session or
                type(binding.service) is not E11Service):
            raise HostHold("Exact session-owned original E11 binding required")
        try:
            project = scope_id(binding.project_id)
        except (TypeError, ValueError) as exc:
            raise HostHold("Native PC project binding invalid") from exc
        if op == "preview":
            command["project_id"] = project
        # scope_id and the original E11 owner service are callback boundaries;
        # do not dispatch or publish after native SID/lease/permissions changed.
        if _scope(session) != before:
            raise HostDenied("Native PC identity changed before original owner dispatch")
        result = binding.service.route_pc_control(command)
        if _scope(session) != before:
            raise HostDenied("Native PC identity changed during original owner callback")
        return result

    def register(self, host, *, receipt):
        if type(host) is not NoxPackHost:
            raise HostHold("Existing PACK01 host required")
        host.bind(ROUTE, BoundPort(self.execute, self._ready, receipt, 1))
        return frozenset({ROUTE})
