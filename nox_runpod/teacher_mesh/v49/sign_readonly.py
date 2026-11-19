"""Trusted owner-side GitHub Actions signer for ONE read-only V49 request.

GitHub Actions must inject NOX_BRIDGE_HMAC_KEY from a protected repository
secret. This module NEVER prints or commits it. One pending request at a time.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys
import time
from .onehost_bridge import INBOX_SCHEMA, SCHEMA, READ, canon, sign_request

INBOX_PATH = Path("coordination/bridge/NOX_BRIDGE_INBOX.json")
ACTIONS = frozenset({
    "server.status", "server.gpus", "server.disk",
    "nox.queue.status", "nox.s03.status", "nox.training.status",
    "nox.model.status", "nox.audit.status",
})
ACTOR = "MSSTXNEWS"


def prepare_request(inbox: dict, *, action: str, actor: str, run_id: str,
                    key: bytes, now: int, target_id: int = 60509551) -> dict:
    if actor != ACTOR:
        raise ValueError("HOLD_NOT_GITHUB_OWNER")
    if action not in ACTIONS or action not in READ:
        raise ValueError("HOLD_SIGNER_ACTION_NOT_ALLOWED")
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("HOLD_BRIDGE_HMAC_KEY_MISSING")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{4,30}", run_id):
        raise ValueError("HOLD_RUN_ID")
    if inbox.get("schema") != INBOX_SCHEMA or inbox.get("instance_id") != target_id:
        raise ValueError("HOLD_SIGNER_INBOX_SCHEMA")
    existing = inbox.get("requests")
    if not isinstance(existing, list) or existing:
        raise ValueError("HOLD_PRIOR_UNACKNOWLEDGED_REQUEST")
    payload = {
        "schema": SCHEMA,
        "request_id": f"V49-{run_id}",
        "instance_id": target_id,
        "action": action,
        "target_id": f"NOX-{target_id}",
        "tenant_id": "NOX_OWNER",
        "principal_id": ACTOR,
        "chat_id": "bridge",
        "issued_at": now,
        "expires_at": now + 300,
        "parameters": {},
    }
    payload["signature"] = sign_request(payload, key)
    return {"schema": INBOX_SCHEMA, "instance_id": target_id,
            "requests": [payload]}


def main() -> int:
    action = os.environ.get("NOX_BRIDGE_ACTION", "")
    actor = os.environ.get("GITHUB_ACTOR", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    secret = os.environ.get("NOX_BRIDGE_HMAC_KEY", "").encode("utf-8")
    try:
        inbox = json.loads(INBOX_PATH.read_text(encoding="utf-8"))
        updated = prepare_request(inbox, action=action, actor=actor,
                                  run_id=run_id, key=secret, now=int(time.time()))
        # Only restricted metadata and HMAC go into repository, never secrets.
        INBOX_PATH.write_bytes(canon(updated) + b"\n")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        # Error strings are fixed codes; do not echo env variables or tokens.
        print("HOLD_SIGNER_PREFLIGHT:" + str(e), file=sys.stderr)
        return 2
    print("NOX_V49_SIGNED_READONLY_REQUEST_STAGED=true")
    print("LIVE_ONEHOST_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
