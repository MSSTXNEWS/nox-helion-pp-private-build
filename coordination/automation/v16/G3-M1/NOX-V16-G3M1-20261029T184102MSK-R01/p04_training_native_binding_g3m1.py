"""Owner-safe P04 route binding for the existing NOX Windows loader.

Stage candidate only: the T06 integrator must bind it to the real existing
native owner and source-lock. It creates no second trainer, host, DB, RAG index,
GPU probe, network route, subprocess, or synthetic training result.

training.start is DANGEROUS and requires fresh native approval by the
existing PACK01 NoxPackHost.execute dispatcher *plus* an owner lease below.
training.evaluate uses the same existing approved owner and checkpoint.
The native host must serialize revocation/consent and worker calls with the
provided owner lease; this adapter is NOT a replacement for native Windows ACL.
"""
from __future__ import annotations

import json
import re
from typing import Callable


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROUTES = {"training.start": "start", "training.evaluate": "evaluate"}
_MAX_WIRE_BYTES = 262_144


class P04NativeTrainingHold(RuntimeError):
    """Explicit unbound/revoked/invalid-evidence HOLD, not success."""


class ExistingP04TrainingBinding:
    """Use ONLY owner-provided, already existing P04 start/evaluate callbacks.

    No methods in this class create a worker. The callbacks MUST be supplied by
    T06 from the verified single native host; absence fails closed. The
    existing PACK01 dispatcher remains responsible for authentication,
    allowed/private_approved scopes and a FRESH dangerous-action consent.
    """

    def __init__(self, *, owner_receipt_sha256: str, owner_lease,
                 native_authorize: Callable, owner_model_and_rights: Callable,
                 existing_backend_ready: Callable, existing_start: Callable,
                 existing_evaluate: Callable, verify_owner_ack: Callable):
        if (type(owner_receipt_sha256) is not str or
                _SHA256.fullmatch(owner_receipt_sha256) is None):
            raise P04NativeTrainingHold("P04_OWNER_RECEIPT_SHA256_REQUIRED")
        if (owner_lease is None or not callable(getattr(owner_lease, "__enter__", None))
                or not callable(getattr(owner_lease, "__exit__", None))):
            raise P04NativeTrainingHold("P04_NATIVE_OWNER_LEASE_REQUIRED")
        callbacks = (native_authorize, owner_model_and_rights,
                     existing_backend_ready, existing_start, existing_evaluate,
                     verify_owner_ack)
        if not all(callable(x) for x in callbacks):
            raise P04NativeTrainingHold("P04_EXISTING_NATIVE_OWNER_PORTS_REQUIRED")
        self.receipt = owner_receipt_sha256
        self._lease = owner_lease
        self._authorize = native_authorize
        self._attest = owner_model_and_rights
        self._ready = existing_backend_ready
        self._callbacks = {"training.start": existing_start,
                           "training.evaluate": existing_evaluate}
        self._verify_ack = verify_owner_ack

    @staticmethod
    def _snapshot_wire(payload: dict) -> dict:
        if type(payload) is not dict:
            raise P04NativeTrainingHold("P04_NATIVE_OWNER_WIRE_INVALID")
        try:
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8", "strict")
            if not 0 < len(raw) <= _MAX_WIRE_BYTES:
                raise ValueError("wire size")
            # Non-string Python mapping keys can serialize to the SAME JSON
            # property name (for example 1 and "1"). Reject the collision at
            # every nesting level instead of silently replacing trusted data.
            def unique_properties(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise P04NativeTrainingHold(
                            "P04_NATIVE_OWNER_JSON_PROPERTY_COLLISION")
                    result[key] = value
                return result
            return json.loads(raw, object_pairs_hook=unique_properties)
        except (ValueError, TypeError, UnicodeError, RecursionError,
                OverflowError) as exc:
            raise P04NativeTrainingHold("P04_NATIVE_OWNER_WIRE_INVALID") from exc

    def ready(self) -> bool:
        try:
            return self._ready() is True
        except Exception:
            return False

    def _call(self, session, payload: dict, route: str) -> dict:
        # Only NoxPackHost.execute may call these methods. Its frozen session,
        # native_approve and source receipt are required by the host contract.
        frozen = self._snapshot_wire(payload)
        # Fail closed if a native owner lease explicitly declines acquisition.
        # Context managers yielding None still represent valid acquired leases;
        # only an explicit False denies the protected training action.
        with self._lease as lease_granted:
            if lease_granted is False:
                raise P04NativeTrainingHold("P04_NATIVE_OWNER_LEASE_DENIED")
            if self._authorize(session, route) is not True:
                raise PermissionError("P04_NATIVE_OWNER_PERMISSION_OR_CONSENT_REVOKED")
            if self._attest(session, route, self.receipt) is not True:
                raise P04NativeTrainingHold("P04_LICENSE_DATASET_MODEL_LOCK_HOLD")
            if not self.ready():
                raise P04NativeTrainingHold("P04_EXISTING_GPU_WORKER_UNAVAILABLE")
            # An actual pre-existing owner action; no subprocess or synthetic ACK.
            raw_ack = self._callbacks[route](session, frozen)
            ack = self._snapshot_wire(raw_ack)
            if (ack.get("route") != route or
                    ack.get("ownerReceiptSha256") != self.receipt or
                    self._verify_ack(session, route,
                                     self._snapshot_wire(ack)) is not True):
                raise P04NativeTrainingHold("P04_OWNER_OBSERVED_ACK_NOT_VERIFIED")
            # Authorization may have been revoked while the owner action ran.
            # A native lease must protect side effects; this only gates result.
            if self._authorize(session, route) is not True:
                raise PermissionError("P04_NATIVE_OWNER_PERMISSION_OR_CONSENT_REVOKED")
            return self._snapshot_wire(ack)

    def start(self, session, payload: dict) -> dict:
        return self._call(session, payload, "training.start")

    def evaluate(self, session, payload: dict) -> dict:
        return self._call(session, payload, "training.evaluate")

    def register(self, dispatcher, *, bind_existing_owner_methods: Callable):
        """Stage both actual PACK01 ports atomically under T06 owner host lock.

        bind_existing_owner_methods MUST be the existing bind_owner_methods
        from PACK01 native_bridge.py. That function handles collisions, source
        receipt, owner-4 identities, dangerous route, probe and rollback.
        """
        if not callable(bind_existing_owner_methods):
            raise P04NativeTrainingHold("P04_EXISTING_PACK01_BINDER_REQUIRED")
        return bind_existing_owner_methods(
            dispatcher, 4, self, dict(_ROUTES),
            receipt=self.receipt, probe=self.ready,
        )
