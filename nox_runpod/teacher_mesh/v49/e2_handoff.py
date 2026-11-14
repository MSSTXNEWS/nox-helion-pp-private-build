"""Executor #2 handoff to the existing V49 OneHost. No daemon or scheduler.

A trusted owner-side signer may prepare up to 8 HMAC-signed READ requests.
Only installed OneHost can process them via v49.onehost_bridge; receipts must
be signed, correlated, S03-durable and read back. Neither creating requests
nor verifying read receipts means a job ran or weights were changed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from pathlib import Path

from nox_runpod.teacher_mesh.v39.native_control import READ, Scope
from nox_runpod.teacher_mesh.v49.onehost_bridge import (
    SCHEMA, INBOX_SCHEMA, RECEIPT_SCHEMA, sign_request, digest,
)

INSTANCE_ID = 60509551
MAP_SCHEMA = "NOX_E2_R60_READ_HANDOFF_V1"
MASTER_SCHEMA = "NOX_R60_SOURCE_PLAN_V1"
LEDGER_SCHEMA = "NOX_ONEHOST_BRIDGE_RECEIPTS_V1"
BASE = Path(__file__).resolve().parents[3]
PLAN = BASE / "coordination/bridge/NOX_E2_R60_READ_HANDOFF.json"
MASTER = BASE / "coordination/NOX_R60_MASTER.json"


def _load(path: Path):
    if not path.is_file() or path.stat().st_size > 200_000:
        raise ValueError("HOLD_SOURCE_MISSING_OR_OVERSIZED")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_plan(plan, master):
    if not isinstance(plan, dict) or plan.get("schema") != MAP_SCHEMA:
        raise ValueError("HOLD_E2_PLAN_SCHEMA")
    if not isinstance(master, dict) or master.get("schema") != MASTER_SCHEMA:
        raise ValueError("HOLD_MASTER_SCHEMA")
    if plan.get("instance_id") != INSTANCE_ID or master.get("instance_id") != INSTANCE_ID:
        raise ValueError("HOLD_INSTANCE_MISMATCH")
    if master.get("onehost_only") is not True or plan.get("no_new_dispatcher") is not True:
        raise ValueError("HOLD_SECOND_DISPATCHER")
    if (master.get("live_queue_verified") is not False or master.get("registered_count") != 0
            or plan.get("live_enqueued_count") != 0):
        raise ValueError("HOLD_LIVE_QUEUE_CHANGED_USE_NATIVE_READBACK")
    task_rows = master.get("tasks", [])
    if not isinstance(task_rows, list) or len(task_rows) != 60:
        raise ValueError("HOLD_MASTER_60")
    master_by_id = {}
    for row in task_rows:
        if not isinstance(row, dict) or not isinstance(row.get("task_id"), str):
            raise ValueError("HOLD_BAD_MASTER_ROW")
        tid = row["task_id"]
        if tid in master_by_id:
            raise ValueError("HOLD_DUPLICATE_MASTER_TASK")
        master_by_id[tid] = row
    if set(master_by_id) != {f"R60-{n:03d}" for n in range(1, 61)}:
        raise ValueError("HOLD_MASTER_MISSING_IDS")
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) != 30:
        raise ValueError("HOLD_E2_30_TASKS")
    mapped = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str):
            raise ValueError("HOLD_BAD_E2_ROW")
        tid = task["task_id"]
        native = master_by_id.get(tid)
        if (tid in mapped or native is None or native.get("owner") != "executor-2"
                or native.get("legacy_task_id") != task.get("legacy_task_id")
                or native.get("depends_on") != task.get("depends_on")):
            raise ValueError("HOLD_E2_OWNER_OR_DEPENDENCY_DRIFT")
        if (native.get("state") != "PENDING_NATIVE_REGISTRATION"
                or native.get("native_queue_id") is not None or native.get("verified") is not False):
            raise ValueError("HOLD_FALSE_REGISTRATION_OR_COMPLETION")
        action = task.get("read_action")
        if (action not in READ or task.get("state") != "READ_PROBE_PLAN_NOT_EXECUTED"
                or task.get("native_receipt") is not None):
            raise ValueError("HOLD_READ_ALLOWLIST")
        mapped[tid] = action
    expected = {f"R60-{i:03d}" for i in list(range(21, 41)) + list(range(51, 61))}
    if set(mapped) != expected or plan.get("source_plan_count") != 30:
        raise ValueError("HOLD_E2_SCOPE")
    return mapped


def prepare_signed_reads(plan, master, selected, *, scope, secret, issued_at, nonce):
    """To be called only by existing trusted owner signer, never from GitHub CI."""
    actions = validate_plan(plan, master)
    if not isinstance(scope, Scope):
        raise ValueError("HOLD_NATIVE_SCOPE")
    scope.validate()
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("HOLD_OWNER_BRIDGE_SIGNING_KEY")
    if (not isinstance(selected, (tuple, list)) or not 1 <= len(selected) <= 8
            or len(set(selected)) != len(selected)):
        raise ValueError("HOLD_BATCH_LIMIT")
    if (type(issued_at) is not int or issued_at <= 0
            or not isinstance(nonce, str) or re.fullmatch(r"[a-z0-9]{12,28}", nonce) is None):
        raise ValueError("HOLD_TRUSTED_TIMESTAMP_OR_NONCE")
    requests = []
    for task_id in selected:
        if task_id not in actions:
            raise ValueError("HOLD_NOT_EXECUTOR2")
        request = {
            "schema": SCHEMA, "instance_id": INSTANCE_ID,
            "request_id": f"e2-{task_id}-{nonce}",
            "action": actions[task_id], "target_id": "NOX-60509551",
            "tenant_id": scope.tenant_id, "principal_id": scope.principal_id,
            "chat_id": scope.chat_id, "issued_at": issued_at,
            "expires_at": issued_at + 180, "parameters": {},
        }
        request["signature"] = sign_request(request, secret)
        requests.append(request)
    return {"schema": INBOX_SCHEMA, "instance_id": INSTANCE_ID, "requests": requests}


def audit_native_read_receipts(inbox, ledger, secret):
    """Verify signed observations, NEVER attest optimizer or queue progress."""
    out = {"state": "HOLD_NATIVE_READ_RECEIPTS", "signed_read_receipts": 0,
           "native_task_ids": [], "queue_enqueued": 0,
           "optimizer_steps_verified": False, "weights_changed": False}
    if not isinstance(secret, bytes) or len(secret) < 32:
        out["state"] = "HOLD_OWNER_KEY"; return out
    if (not isinstance(inbox, Mapping) or inbox.get("schema") != INBOX_SCHEMA
            or inbox.get("instance_id") != INSTANCE_ID
            or not isinstance(ledger, Mapping) or ledger.get("schema") != LEDGER_SCHEMA
            or ledger.get("instance_id") != INSTANCE_ID):
        out["state"] = "HOLD_BRIDGE_SCHEMA"; return out
    reqs = inbox.get("requests")
    receipts = ledger.get("receipts")
    if not isinstance(reqs, list) or not isinstance(receipts, list) or len(reqs) > 8:
        return out
    ids = [x.get("request_id") for x in reqs if isinstance(x, Mapping)]
    if len(ids) != len(reqs) or len(set(ids)) != len(ids):
        out["state"] = "HOLD_REPLAY_DUPLICATES"; return out
    good = 0
    for r in reqs:
        payload = dict(r)
        request_signature = payload.pop("signature", None)
        if not isinstance(request_signature, str):
            continue
        if not hmac.compare_digest(request_signature, sign_request(payload, secret)):
            continue
        same = [x for x in receipts if isinstance(x, Mapping)
                and x.get("request_id") == r.get("request_id")]
        if len(same) != 1:
            continue
        response = dict(same[0])
        receipt_signature = response.pop("receipt_signature", None)
        if (not isinstance(receipt_signature, str)
                or not hmac.compare_digest(receipt_signature, sign_request(response, secret))):
            continue
        if (response.get("schema") == RECEIPT_SCHEMA
                and response.get("request_sha256") == digest(payload)
                and response.get("action") == r.get("action")
                and response.get("state") == "READ_ONLY_FROM_NATIVE_ONEHOST"
                and response.get("native_readback") is True
                and response.get("s03_durable") is True
                and response.get("performed") is False
                and response.get("independent_verified") is False
                and isinstance(response.get("data_sha256"), str)
                and re.fullmatch(r"[a-f0-9]{64}", response["data_sha256"])):
            good += 1
    out["signed_read_receipts"] = good
    if good and good == len(reqs):
        out["state"] = "SIGNED_S03_NATIVE_OBSERVATIONS_ONLY"
    return out
