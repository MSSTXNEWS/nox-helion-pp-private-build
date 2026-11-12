#!/usr/bin/env python3
"""NOX GENESIS: read-only, fail-closed progress receipt adapter for EXISTING OneHost.

This is not a trainer, endpoint or proof that a GPU job happened.
The trusted existing OneHost must source and authorize the receipts.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import re

SCHEMA = "nox-genesis-live-evidence-v1"
SHA = re.compile(r"^[a-f0-9]{64}$")
URL = re.compile(r"^(?:https://|s03://|nox-checkpoint://|github://)[^\\s]{1,900}$")

def _utc(s: Any):
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None

def _hold(reason: str):
    return {
        "schema": SCHEMA,
        "state": "HOLD",
        "reason": reason,
        "neural_training_confirmed": False,
        "training": None,
        "quality": None,
        "memory": None,
        "source": None,
    }

def normalize_live_receipt(receipt: dict | None, *, now_utc: datetime | None = None, max_age_sec: int = 900) -> dict:
    """Validate receipt format and freshness. This alone NEVER proves optimizer updates."""
    if not isinstance(receipt, dict):
        return _hold("NO_TRUSTED_ONEHOST_RECEIPT")
    if receipt.get("schema") != "nox-onehost-training-receipt-v1":
        return _hold("UNRECOGNIZED_TRAINER_SCHEMA")
    if receipt.get("origin") != "existing_onehost":
        return _hold("UNTRUSTED_PRODUCER")
    stamp = _utc(receipt.get("observed_at_utc"))
    now = now_utc or datetime.now(timezone.utc)
    if stamp is None or stamp > now + timedelta(seconds=30):
        return _hold("INVALID_RECEIPT_TIME")
    if (now - stamp).total_seconds() > max_age_sec:
        return _hold("STALE_TRAINER_RECEIPT")
    sha = receipt.get("student_model_sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return _hold("NO_STUDENT_SHA")
    steps = receipt.get("optimizer_steps")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 0:
        return _hold("OPTIMIZER_COUNT_NOT_VERIFIED")
    ckpt = receipt.get("checkpoint_sha256")
    if ckpt is not None and (not isinstance(ckpt, str) or not SHA.fullmatch(ckpt)):
        return _hold("INVALID_CHECKPOINT_SHA")
    proof_uri = receipt.get("evidence_uri")
    if not isinstance(proof_uri, str) or not URL.fullmatch(proof_uri):
        return _hold("MISSING_EVIDENCE_LOCATION")

    evaluation = receipt.get("evaluation")
    quality = None
    if isinstance(evaluation, dict) and evaluation.get("same_harness") is True and evaluation.get("heldout") is True:
        name = evaluation.get("benchmark")
        numerator = evaluation.get("correct")
        denominator = evaluation.get("total")
        if (isinstance(name, str) and 1 <= len(name) <= 80 and
            type(numerator) is int and type(denominator) is int and
            0 <= numerator <= denominator and denominator > 0 and denominator <= 1_000_000):
            quality = {
                "benchmark": name,
                "correct": numerator,
                "total": denominator,
                "score": round(numerator / denominator, 6),
                "model_sha256": sha,
                "state": "RECEIPT_EVALUATION_NOT_INDEPENDENTLY_REPLAYED",
            }
    memory = receipt.get("s03")
    s03 = None
    if isinstance(memory, dict):
        s03 = {
            "state": "CONNECTED_BY_TRUSTED_HOST" if memory.get("authenticated") is True and
                     memory.get("readback_verified") is True else "HOLD_S03_UNVERIFIED",
            "last_readback_at_utc": memory.get("last_readback_at_utc") if
            _utc(memory.get("last_readback_at_utc")) else None,
        }

    return {
        "schema": SCHEMA,
        "state": "RECEIPT_FORMAT_VALIDATED_NOT_GPU_REPLAYED",
        "neural_training_confirmed": False,
        "training": {
            "model_sha256": sha,
            "optimizer_steps_claimed": steps,
            "checkpoint_sha256": ckpt,
            "observed_at_utc": receipt["observed_at_utc"],
            "signal": "REPORTED_BY_EXISTING_ONEHOST_NOT_INDEPENDENTLY_CONFIRMED",
        },
        "quality": quality,
        "memory": s03,
        "source": proof_uri,
    }

def web_payload(trusted_onehost_callback, *, now_utc: datetime | None = None) -> dict:
    """Called by the EXISTING authenticated OneHost route, never by a new server."""
    if not callable(trusted_onehost_callback):
        return _hold("ONEHOST_CALLBACK_NOT_BOUND")
    try:
        raw = trusted_onehost_callback()
    except Exception:
        return _hold("ONEHOST_RECEIPT_UNAVAILABLE")
    return normalize_live_receipt(raw, now_utc=now_utc)
