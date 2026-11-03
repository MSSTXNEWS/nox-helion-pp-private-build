"""Media and rights receipts (M2.4 / M2.5).

Receipts record what was observed or decided.
They do not themselves authorize use.
"""
from __future__ import annotations

import hashlib
import time
from typing import Mapping


def media_receipt(
    *,
    asset_id: str,
    sha256: str,
    kind: str,
    source: str,
) -> dict:
    """Record a media asset observation."""
    if not all(isinstance(x, str) and x.strip() for x in (asset_id, sha256, kind, source)):
        raise ValueError("MEDIA_RECEIPT_FIELDS_REQUIRED")
    if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256.lower()):
        raise ValueError("SHA256_INVALID")
    return {
        "schema": "NOX-MEDIA-RECEIPT-v1",
        "asset_id": asset_id,
        "sha256": sha256.lower(),
        "kind": kind,
        "source": source,
        "ts": int(time.time()),
        "usage_authorized": False,
    }


def rights_receipt(
    *,
    asset_id: str,
    decision: str,
    evidence: Mapping | None = None,
) -> dict:
    """Record a rights decision."""
    if decision not in ("ALLOWED", "DENIED", "REVIEW_REQUIRED"):
        raise ValueError("RIGHTS_DECISION_INVALID")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ValueError("ASSET_ID_REQUIRED")
    return {
        "schema": "NOX-RIGHTS-RECEIPT-v1",
        "asset_id": asset_id,
        "decision": decision,
        "evidence": dict(evidence or {}),
        "ts": int(time.time()),
        "usage_authorized": decision == "ALLOWED",
    }


def receipt_id(receipt: Mapping) -> str:
    """Stable short id for a receipt."""
    raw = f"{receipt.get('schema')}:{receipt.get('asset_id')}:{receipt.get('ts')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]
