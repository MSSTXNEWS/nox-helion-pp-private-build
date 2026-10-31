"""NOX OIE future donor: host-side admission to the EXISTING OIE engine.

No extra PACK01 route, WebView permission, process, server, DB or file writes.
Only the authenticated original E06 Windows owner may call this helper.
SOURCE-ONLY: a real E06 host owner must wire and E07 must verify.
"""
from __future__ import annotations

import json
import re

_ALLOWED = frozenset(("idea.list", "idea.inspect", "mission.run", "megablock1.preview"))
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
_FORBIDDEN = frozenset(("tenant", "principal", "windows_sid", "session_id", "scopes",
                       "nativeConsent", "native_approve", "admin", "private_approved",
                       "consent", "api_key", "token", "secret", "url", "path"))
_MAX_REPLY = 512 * 1024


class OieNativeHold(RuntimeError):
    """A failed native check can never be treated as an ACK."""


def dispatch_oie_owner(*, scope, action, parameters, authorize, run_existing_job):
    """Trusted native-only call. Scope type comes from immutable PACK01."""
    from nox_native_bridge import NativeSession

    if type(scope) is not NativeSession:
        raise PermissionError("OIE_AUTHENTICATED_NATIVE_SCOPE_REQUIRED")
    scope.validate()
    if not callable(authorize) or not callable(run_existing_job):
        raise OieNativeHold("OIE_OWNER_BOUND_CALLBACKS_MISSING")
    if type(action) is not str or action not in _ALLOWED:
        raise PermissionError("OIE_ACTION_NOT_IN_CONTRACT")
    if type(parameters) is not dict:
        raise ValueError("OIE_PARAMETERS_NOT_OBJECT")
    if any(type(k) is not str or k in _FORBIDDEN or k.startswith("_")
           for k in parameters):
        raise PermissionError("OIE_PAGE_AUTHORITY_OR_UNKNOWN_FIELD_DENIED")
    if action == "idea.list":
        if parameters:
            raise ValueError("OIE_LIST_EXACT_EMPTY_PARAMETERS_REQUIRED")
        payload = {"contract": "nox.oie.job.v1", "action": action}
    elif action == "idea.inspect":
        if set(parameters) != {"idea_id"}:
            raise ValueError("OIE_INSPECT_EXACT_ID_REQUIRED")
        idea_id = parameters["idea_id"]
        if type(idea_id) is not str or not _ID.fullmatch(idea_id):
            raise ValueError("OIE_INSPECT_ID_INVALID")
        payload = {"contract": "nox.oie.job.v1", "action": action,
                   "idea_id": idea_id}
    else:
        if not set(parameters).issubset({"theme", "count", "seed"}):
            raise PermissionError("OIE_JOB_UNKNOWN_FIELD")
        theme = parameters.get("theme", "")
        count = parameters.get("count", 3)
        seed = parameters.get("seed", 0)
        if (type(theme) is not str or len(theme) > 240 or
                any(ord(c) < 32 for c in theme)):
            raise ValueError("OIE_THEME_INVALID")
        if type(count) is not int or not 1 <= count <= 12:
            raise ValueError("OIE_COUNT_INVALID")
        if type(seed) is not int or not -1000000 <= seed <= 1000000:
            raise ValueError("OIE_SEED_INVALID")
        payload = {"contract": "nox.oie.job.v1", "action": action,
                   "parameters": {"theme": theme, "count": count, "seed": seed}}

    # Native callback MUST use independently obtained Windows session/ACL,
    # not a value in the WebView request. In particular, no "browser success"
    # or local test token grants authorization.
    if authorize(scope, "nox.oie.job.v1", action) is not True:
        raise PermissionError("OIE_OWNER_CAPABILITY_OR_CONSENT_DENIED")
    result = run_existing_job(payload)
    if (type(result) is not dict or result.get("ok") is not True or
            result.get("contract") != "nox.oie.result.v1" or
            type(result.get("result")) is not dict):
        raise OieNativeHold("OIE_EXISTING_ENGINE_RESULT_NOT_VERIFIED")
    try:
        wire = json.dumps(result, allow_nan=False, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise OieNativeHold("OIE_ENGINE_RESULT_UNSAFE_JSON") from exc
    if len(wire) > _MAX_REPLY:
        raise OieNativeHold("OIE_NATIVE_REPLY_TOO_LARGE")
    # Do not claim E07, commercial success, new business or verified market.
    return json.loads(wire)
