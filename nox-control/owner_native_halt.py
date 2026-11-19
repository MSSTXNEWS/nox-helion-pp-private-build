#!/usr/bin/env python3
"""Dedicated owner-only route to the existing exact trainer halt.

This invokes only owner_native_repair.halt_main(). It never stops model, chat,
web, dispatcher, or an arbitrary PID and does not claim cgroup RAM reclamation.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

EXPECTED_SERVICE = "nox-train-volta-t866u"
EXPECTED_WRAPPER = Path("/root/nox/scripts/run_train_volta_t866u.sh")
EXPECTED_TRAINER = Path("/root/nox/scripts/train_qlora_35b_t866u.py")
EXPECTED_SOURCE_PINS = {
    "run_train_volta_t866u.sh":
        "daeb0b2b90d8a3717ecb8e78c2481697b5f209ce18646ae893e377c0de538b99",
    "train_qlora_35b_t866u.py":
        "703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a",
}


def require(value, reason):
    if not value:
        raise RuntimeError("HOLD_OWNER_HALT_" + reason)


def main():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    require(re.fullmatch(r"[0-9]{1,24}", request) is not None, "REQUEST_CONTEXT")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None, "SOURCE_CONTEXT")
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == {"owner_native_repair.py"},
            "BUNDLE_SCOPE")
    row = BUNDLE["owner_native_repair.py"]
    require(isinstance(row, dict) and set(row) == {"content", "sha256"},
            "BUNDLE_SCHEMA")
    try:
        raw = base64.b64decode(row["content"], validate=True)
    except (ValueError, TypeError):
        raise RuntimeError("HOLD_OWNER_HALT_BUNDLE_ENCODING")
    require(0 < len(raw) <= 65536, "BUNDLE_SIZE")
    require(hashlib.sha256(raw).hexdigest() == row["sha256"], "BUNDLE_DIGEST")
    try:
        code = compile(raw, "<pinned-owner-native-repair>", "exec")
    except (SyntaxError, ValueError):
        raise RuntimeError("HOLD_OWNER_HALT_SOURCE_SYNTAX")

    module = types.ModuleType("_nox_owner_native_repair_halt")
    module.__file__ = "<pinned-owner-native-repair>"
    exec(code, module.__dict__)
    require(getattr(module, "SERVICE", None) == EXPECTED_SERVICE, "SERVICE_SCOPE")
    require(getattr(module, "WRAPPER", None) == EXPECTED_WRAPPER, "WRAPPER_SCOPE")
    require(getattr(module, "TRAINER", None) == EXPECTED_TRAINER, "TRAINER_SCOPE")
    require(getattr(module, "SOURCE_PINS", None) == EXPECTED_SOURCE_PINS,
            "SOURCE_PINS")
    halt = getattr(module, "halt_main", None)
    require(callable(halt), "HALT_ENTRY_MISSING")

    # halt_main itself verifies fresh Supervisor/PID/starttime/argv/CUDA identity,
    # writes and retains the training hold, and verifies its native receipt.
    # No cgroup memory reclaim or 2 GiB headroom is inferred here.
    result = halt()
    require(result == 0, "NATIVE_HALT_NOT_VERIFIED")
    print("NOX_MAINT_HALT_TARGET=" + EXPECTED_SERVICE, flush=True)
    print("NOX_MAINT_HALT_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"HOLD_OWNER_HALT_[A-Z0-9_]+", code):
            code = "HOLD_OWNER_HALT_" + type(exc).__name__.upper()
        print("NOX_MAINT_RESULT=" + code, flush=True)
        sys.exit(2)
