"""Win64 host lease and license ACK (M2.2).

Lease is short-lived and tied to an authorized Windows x64 host.
License ACK is recorded; does not grant rights by itself.
"""
from __future__ import annotations

import hashlib
import time
from typing import Mapping

LEASE_TTL_SEC = 3600  # 1 hour


def issue_lease(*, host_id: str, owner_receipt: str) -> dict:
    """Issue a short-lived lease for an authorized host."""
    if not isinstance(host_id, str) or not host_id.strip():
        raise ValueError("HOST_ID_REQUIRED")
    if not isinstance(owner_receipt, str) or not owner_receipt.strip():
        raise ValueError("OWNER_RECEIPT_REQUIRED")
    now = int(time.time())
    token = hashlib.sha256(f"{host_id}:{owner_receipt}:{now}".encode()).hexdigest()[:32]
    return {
        "schema": "NOX-WIN64-LEASE-v1",
        "host_id": host_id,
        "token": token,
        "issued_at": now,
        "expires_at": now + LEASE_TTL_SEC,
        "owner_receipt": owner_receipt,
        "status": "ACTIVE",
    }


def check_lease(lease: Mapping, *, now: int | None = None) -> bool:
    """Return True if the lease is still valid."""
    if not isinstance(lease, Mapping):
        return False
    exp = lease.get("expires_at")
    if not isinstance(exp, int):
        return False
    now = now if now is not None else int(time.time())
    return now < exp and lease.get("status") == "ACTIVE"


def license_ack(*, lease_token: str, license_id: str, accepted: bool) -> dict:
    """Record a license acknowledgement under a valid lease."""
    if not isinstance(lease_token, str) or not lease_token:
        raise ValueError("LEASE_TOKEN_REQUIRED")
    if not isinstance(license_id, str) or not license_id:
        raise ValueError("LICENSE_ID_REQUIRED")
    return {
        "schema": "NOX-LICENSE-ACK-v1",
        "lease_token": lease_token,
        "license_id": license_id,
        "accepted": accepted is True,
        "ts": int(time.time()),
        "status": "ACKNOWLEDGED" if accepted is True else "DECLINED",
    }
