"""Fail-closed admission gate shared by legacy GPU training entrypoints.

Training is denied unless a pinned, owner-authorized manifest names the exact
trainable DeepSeek target. Quantized inference artifacts and the historical
NOX_9B_UNIFIED student are never admitted by this gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

AUTHORIZED_TARGET = "deepseek-v4.1-flash-1017-trainable"
DEFAULT_STOP_PATHS = (Path("/workspace/nox/STOP"), Path("/workspace/nox/MODEL_UPDATE"))


def admission_hold_reason(env=None, stop_paths=DEFAULT_STOP_PATHS, expected_target=AUTHORIZED_TARGET):
    """Return a HOLD reason or None. No filesystem writes or model imports occur."""
    env = os.environ if env is None else env
    if any(Path(path).exists() for path in stop_paths):
        return "STOP_OR_MODEL_UPDATE_PRESENT"
    if env.get("NOX_TRAINING_ADMISSION") != "AUTHORIZED":
        return "EXPLICIT_TRAINING_ADMISSION_REQUIRED"
    if expected_target not in {AUTHORIZED_TARGET, "NOX_9B_UNIFIED"}:
        return "TARGET_NOT_AUTHORIZED"
    if env.get("NOX_TRAINING_TARGET") != expected_target:
        return "TARGET_NOT_AUTHORIZED"
    manifest_raw = env.get("NOX_TRAINING_MANIFEST")
    expected_sha = env.get("NOX_TRAINING_MANIFEST_SHA256", "").lower()
    if not manifest_raw or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        return "PINNED_MODEL_MANIFEST_REQUIRED"
    try:
        raw = Path(manifest_raw).read_bytes()
    except OSError:
        return "MODEL_MANIFEST_UNREADABLE"
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        return "MODEL_MANIFEST_SHA256_MISMATCH"
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "MODEL_MANIFEST_INVALID_JSON"
    if not isinstance(manifest, dict) or manifest.get("status") != "AUTHORIZED":
        return "MODEL_MANIFEST_NOT_AUTHORIZED"
    if manifest.get("target_model") != expected_target:
        return "MODEL_MANIFEST_TARGET_MISMATCH"
    if manifest.get("trainable_base") is not True:
        return "TRAINABLE_BASE_NOT_VERIFIED"
    if manifest.get("license_status") != "VERIFIED":
        return "LICENSE_NOT_VERIFIED"
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(manifest.get("source_revision", "")).lower()):
        return "SOURCE_REVISION_NOT_PINNED"
    if manifest.get("quantized_inference_only") is not False:
        return "QUANTIZED_OR_INFERENCE_ONLY_BASE"
    return None
