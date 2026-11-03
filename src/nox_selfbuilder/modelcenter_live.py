"""ModelCenter live actions.

Buttons call the real provider and progress tracker.
No silent weight mutation. Training remains a handoff.
"""
from __future__ import annotations

import json
from pathlib import Path

from .live_ollama_provider import ensure_primary_model, self_describe
from .modelcenter_progress import make_progress, make_receipt, write_receipt
from .worms import WormHold

RECEIPT_PATH = Path("artifacts/modelcenter_receipts.jsonl")


def status(*, host: str = "http://127.0.0.1:11434") -> dict:
    """Return live model status."""
    try:
        model = ensure_primary_model(host=host)
        return {
            "schema": "NOX-MODELCENTER-STATUS-v1",
            "model": model,
            "status": "LIVE",
            "host": host,
        }
    except WormHold as exc:
        return {
            "schema": "NOX-MODELCENTER-STATUS-v1",
            "model": None,
            "status": "OFFLINE",
            "error": str(exc),
            "host": host,
        }


def download_weights(*, tag: str = "qwen2.5-coder:7b") -> dict:
    """Record download request. Actual fetch stays in engines/fetch_ollama_weight_layers.py."""
    progress = make_progress(action="download", tag=tag, status="REQUESTED")
    receipt = make_receipt(
        action="download",
        tag=tag,
        outcome="HOLD",
        evidence={"note": "Use engines/fetch_ollama_weight_layers.py --execute on authorized host"},
    )
    write_receipt(RECEIPT_PATH, receipt)
    return {"progress": progress, "receipt": receipt}


def start_training(*, tag: str = "qwen2.5-coder:7b") -> dict:
    """Record LoRA training request. Real training requires GPU + P04."""
    progress = make_progress(action="train", tag=tag, status="REQUESTED")
    receipt = make_receipt(
        action="train",
        tag=tag,
        outcome="HOLD",
        evidence={"note": "LoRA training requires authorized GPU host and P04 gate"},
    )
    write_receipt(RECEIPT_PATH, receipt)
    return {"progress": progress, "receipt": receipt}


def describe(*, host: str = "http://127.0.0.1:11434") -> dict:
    """Run self-description on the live model."""
    try:
        result = self_describe(host=host)
        receipt = make_receipt(
            action="self_describe",
            tag=result.get("model", "unknown"),
            outcome="OK",
            evidence={"response": result.get("response", "")[:500]},
        )
        write_receipt(RECEIPT_PATH, receipt)
        return {"result": result, "receipt": receipt}
    except WormHold as exc:
        receipt = make_receipt(
            action="self_describe",
            tag="unknown",
            outcome="FAILED",
            evidence={"error": str(exc)},
        )
        write_receipt(RECEIPT_PATH, receipt)
        return {"error": str(exc), "receipt": receipt}


def list_receipts(limit: int = 20) -> list[dict]:
    """Return last N receipts."""
    if not RECEIPT_PATH.exists():
        return []
    lines = RECEIPT_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
