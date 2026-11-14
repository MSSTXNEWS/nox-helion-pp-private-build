"""NOX V49: owner-authenticated outbound bridge into EXISTING OneHost.

No HTTP listener, subprocess, model, S03 database, scheduler, or GPU process.
The existing OneHost timer injects native ports and calls poll_once(...).
Only V39 allowlisted READ actions are available. All write operations are
intentionally absent until a separate owner/native approval path exists.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import time
from typing import Any

from nox_runpod.teacher_mesh.v39.native_control import NativeAdmin, Scope, READ

SCHEMA = "NOX_ONEHOST_BRIDGE_REQUEST_V1"
INBOX_SCHEMA = "NOX_ONEHOST_BRIDGE_INBOX_V1"
RECEIPT_SCHEMA = "NOX_ONEHOST_BRIDGE_RECEIPT_V1"
ID_RE = re.compile(r"^[A-Za-z0-9._:@/-]{8,128}$")
SIG_RE = re.compile(r"^[0-9a-f]{64}$")
KEYS = frozenset({
    "schema", "request_id", "instance_id", "action", "target_id",
    "tenant_id", "principal_id", "chat_id", "issued_at", "expires_at",
    "parameters", "signature",
})


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def sign_request(payload: Mapping[str, Any], secret: bytes) -> str:
    """For trusted OWNER-side signer only; never feed a secret from repository."""
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("HOLD_BRIDGE_SIGNING_KEY")
    body = dict(payload)
    body.pop("signature", None)
    return hmac.new(secret, canon(body), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class NativePorts:
    # These must be the installed OneHost/S03 callbacks, NOT in-memory substitutes.
    stop: Callable[[], bool]
    claim_request: Callable[[str, str], bool]  # atomic durable idempotency claim
    append_s03: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    verify_s03: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


class OutboundOneHostBridge:
    def __init__(self, admin: NativeAdmin, ports: NativePorts, key: bytes,
                 *, instance_id: int = 60509551, max_batch: int = 8,
                 clock: Callable[[], float] = time.time):
        if not isinstance(admin, NativeAdmin):
            raise TypeError("EXISTING_NATIVE_ADMIN_REQUIRED")
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("HOLD_BRIDGE_AUTH_KEY")
        if type(instance_id) is not int or instance_id < 1:
            raise ValueError("HOLD_INSTANCE")
        if type(max_batch) is not int or max_batch < 1 or max_batch > 8:
            raise ValueError("HOLD_MAX_BATCH")
        if any(not callable(getattr(ports, n, None)) for n in
               ("stop", "claim_request", "append_s03", "verify_s03")):
            raise TypeError("EXISTING_S03_PORTS_REQUIRED")
        self.admin = admin
        self.ports = ports
        self.key = key
        self.instance_id = instance_id
        self.max_batch = max_batch
        self.clock = clock

    def _valid(self, req: Any) -> tuple[bool, str]:
        if not isinstance(req, dict) or set(req) != KEYS:
            return False, "HOLD_REQUEST_SCHEMA"
        if req.get("schema") != SCHEMA or req.get("instance_id") != self.instance_id:
            return False, "HOLD_WRONG_TARGET"
        if req.get("action") not in READ or req.get("parameters") != {}:
            return False, "HOLD_ACTION_NOT_READ_ONLY"
        if not isinstance(req.get("request_id"), str) or not ID_RE.fullmatch(req["request_id"]):
            return False, "HOLD_REQUEST_ID"
        if any(not isinstance(req.get(k), str) for k in ("target_id", "tenant_id", "principal_id", "chat_id")):
            return False, "HOLD_SCOPE"
        if any(type(req.get(k)) is not int for k in ("issued_at", "expires_at")):
            return False, "HOLD_TIME_FORMAT"
        now = int(self.clock())
        if req["issued_at"] > now + 30 or req["expires_at"] <= now:
            return False, "HOLD_EXPIRED_OR_FUTURE"
        if req["expires_at"] - req["issued_at"] > 300 or req["expires_at"] <= req["issued_at"]:
            return False, "HOLD_TTL"
        if not isinstance(req.get("signature"), str) or not SIG_RE.fullmatch(req["signature"]):
            return False, "HOLD_SIGNATURE_FORMAT"
        try:
            signed = sign_request(req, self.key)
            if not hmac.compare_digest(signed, req["signature"]):
                return False, "HOLD_BAD_SIGNATURE"
            # Validate NativeAdmin scope constraints before claiming the ID.
            Scope(req["tenant_id"], req["principal_id"], req["chat_id"]).validate()
        except (TypeError, ValueError, UnicodeError):
            return False, "HOLD_REQUEST_VALIDATION"
        return True, "OK"

    def process_one(self, req: Any) -> dict[str, Any]:
        ok, state = self._valid(req)
        if not ok:
            return {"schema": RECEIPT_SCHEMA, "state": state, "performed": False}
        request_id = req["request_id"]
        request_sha = digest({k: v for k, v in req.items() if k != "signature"})
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA, "request_id": request_id,
            "action": req["action"], "request_sha256": request_sha,
            "performed": False, "native_readback": False,
            "independent_verified": False,
        }
        try:
            if self.ports.stop() is not False:
                return {**receipt, "state": "HOLD_STOP"}
            # Atomic claim in the EXISTING S03; must survive restart.
            if self.ports.claim_request(request_id, request_sha) is not True:
                return {**receipt, "state": "HOLD_REPLAY_OR_S03_UNAVAILABLE"}
            if self.ports.stop() is not False:
                return {**receipt, "state": "HOLD_STOP_AFTER_CLAIM"}
            scope = Scope(req["tenant_id"], req["principal_id"], req["chat_id"])
            result = self.admin.invoke(req["action"], req["target_id"], scope,
                                       request_id, parameters={})
            native_read = result.get("state") == "READ_ONLY_FROM_NATIVE_ONEHOST"
            # Never export live admin data to the repository; digest only.
            event = {"schema": RECEIPT_SCHEMA, "request_id": request_id,
                     "request_sha256": request_sha, "action": req["action"],
                     "native_state": str(result.get("state", "HOLD_NATIVE"))[:80],
                     "native_readback": native_read,
                     "data_sha256": digest(result.get("data", {})) if native_read else None}
            ack = self.ports.append_s03(event)
            if not isinstance(ack, Mapping) or self.ports.verify_s03(ack, event) is not True:
                return {**receipt, "state": "HOLD_S03_AUDIT_UNVERIFIED"}
            receipt.update({"state": event["native_state"],
                            "native_readback": native_read,
                            "data_sha256": event["data_sha256"],
                            "s03_durable": True})
            return receipt
        except Exception:
            # No retry: the claim or native call may already have happened.
            return {**receipt, "state": "HOLD_NATIVE_OR_S03_EXCEPTION",
                    "performed": "UNKNOWN"}

    def poll_once(self, inbox: Mapping[str, Any], publish: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
        """One bounded tick invoked from existing OneHost scheduler only."""
        if not isinstance(inbox, Mapping) or inbox.get("schema") != INBOX_SCHEMA:
            return {"state": "HOLD_INBOX_SCHEMA", "published": 0}
        if inbox.get("instance_id") != self.instance_id:
            return {"state": "HOLD_INBOX_TARGET", "published": 0}
        requests = inbox.get("requests")
        if not isinstance(requests, list) or len(requests) > self.max_batch:
            return {"state": "HOLD_BATCH_SIZE", "published": 0}
        if not callable(publish):
            return {"state": "HOLD_PUBLISH_PORT", "published": 0}
        published = 0
        for req in requests:
            outcome = self.process_one(req)
            # Do not publish unsigned request errors. OneHost keeps local audit.
            if outcome.get("request_id") is None:
                continue
            outcome["receipt_signature"] = sign_request(outcome, self.key)
            try:
                if publish(outcome) is not True:
                    return {"state": "HOLD_RECEIPT_PUBLICATION",
                            "published": published, "may_have_processed": True}
            except Exception:
                return {"state": "HOLD_RECEIPT_PUBLICATION",
                        "published": published, "may_have_processed": True}
            published += 1
        return {"state": "ONEHOST_BRIDGE_TICK_FINISHED",
                "published": published, "native_queue_registered": 0,
                "weights_changed": False, "production_accepted": False}
