"""E06 source overlay for the ORIGINAL helion.app process.

Uses the one legacy Store, original localhost model inventory and existing
PACK01/NativeIngress framed protocol. No second DB, HTTP host, LLM or UI.
Production native WPF activation remains separately gated by Windows E2E.
"""
from __future__ import annotations
import getpass
import hashlib
import json
import sys
from pathlib import Path

from nox_native_bridge import NoxPackHost, NativeSession, BoundPort, APPROVED_NATIVE_POLICY
from p02_native_ingress import NativeIngress
from p02_framed_worker import serve_native_frames
from .local_model import discover_installed_local_models


def serve_existing_store(store, run_id: str) -> int:
    if not hasattr(store, "conn") or not callable(getattr(store.conn, "execute", None)):
        raise RuntimeError("E06_ORIGINAL_STORE_REQUIRED")
    if type(run_id) is not str or not 1 <= len(run_id) <= 128 or any(
            not 32 <= ord(c) <= 126 for c in run_id):
        raise ValueError("E06_NATIVE_RUNID_INVALID")
    principal = getpass.getuser().strip()
    if not principal or len(principal) > 128:
        raise PermissionError("E06_WINDOWS_USER_REQUIRED")
    # Canonical route/owner/risk table from the approved existing PACK01 code,
    # not from WebView2 JSON. Only a read-only model inventory port is bound.
    catalog = {"version": "NOX-INTEGRATION-PACK-01",
               "actions": [{"taskId": f"NIP01-{i:02d}", "routeId": name,
                            "owner": owner, "risk": risk, "settings": []}
                           for i, (name, owner, risk)
                           in enumerate(APPROVED_NATIVE_POLICY, 1)]}
    dispatcher = NoxPackHost(catalog)
    scope = NativeSession("local", principal, "default",
                          allowed=frozenset({"chat.model"}))
    evidence = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def installed_models(_session, args):
        if type(args) is not dict or args:
            raise PermissionError("E06_MODEL_INVENTORY_REQUIRES_EMPTY_PAYLOAD")
        try:
            actual = discover_installed_local_models()
        except (OSError, ConnectionError, TimeoutError):
            return {"models": [], "provider_state": "OFFLINE",
                    "source": "ORIGINAL_LOCAL_DISCOVERY"}
        if isinstance(actual, dict):
            actual = actual.get("models")
        if not isinstance(actual, (list, tuple)):
            raise RuntimeError("E06_ORIGINAL_MODEL_INVENTORY_INVALID")
        names = []
        for item in actual:
            value = item if isinstance(item, str) else (
                item.get("name") if isinstance(item, dict) else None)
            if not isinstance(value, str) or not 1 <= len(value) <= 256:
                raise RuntimeError("E06_ORIGINAL_MODEL_NAME_INVALID")
            if value in names:
                raise RuntimeError("E06_ORIGINAL_MODEL_DUPLICATE")
            names.append(value)
            if len(names) > 256:
                raise RuntimeError("E06_MODEL_INVENTORY_OVERSIZE")
        return {"models": names, "provider_state": "DISCOVERY_RESPONDED",
                "source": "ORIGINAL_LOCAL_DISCOVERY"}

    dispatcher.bind("chat.model", BoundPort(installed_models, lambda: True,
                                            evidence, 2))
    ingress = NativeIngress(dispatcher, lambda: scope,
                            expected_run_id=run_id)
    # stdout must contain ONLY authenticated binary P02 frames.
    serve_native_frames(ingress, sys.stdin.buffer, sys.stdout.buffer)
    return 0
