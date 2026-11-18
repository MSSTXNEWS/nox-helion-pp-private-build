#!/usr/bin/env python3
"""Source-only, exact pinned UI terminal placeholder repair for NOX V24.

This module never contacts a server, imports serving modules, or modifies files.
It produces candidate bytes only; an independently reviewed installer must bind
the resulting SHA and follow current owner admission/rollback requirements.
"""
from __future__ import annotations

import hashlib
import re

EXPECTED_INPUT_SHA256 = "646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2"

ANCHORS = (
    ("  /* ---- stream + live typing dots until the first token ---- */",
     "  /* ---- stream + live typing dots until the first token ---- */\n"
     "  const noSubstantiveReply = value => !String(value || '').trim() || "
     "/^[\\u2014\\u2013-]+$/.test(String(value).trim());"),
    ("if (!run.stopped && done?.status === 'done' && !result.trim())",
     "if (!run.stopped && done?.status === 'done' && noSubstantiveReply(result))"),
    ("if (!result.trim()) { out.body.textContent = notice; out.box.dataset.source = 'SYSTEM_NOTICE'; }",
     "if (noSubstantiveReply(result)) { out.body.textContent = notice; "
     "out.box.dataset.source = 'SYSTEM_NOTICE'; }"),
    ("else if (!result.trim()) out.body.textContent = done.status === 'STOP_FLAG'",
     "else if (noSubstantiveReply(result)) out.body.textContent = done.status === 'STOP_FLAG'"),
)


def prepare(raw: bytes, expected_sha256: str = EXPECTED_INPUT_SHA256) -> bytes:
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 131072
            or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ValueError("HOLD_CHAT_UI_SOURCE_PIN")
    text = raw.decode("utf-8")
    for old, new in ANCHORS:
        if text.count(old) != 1:
            raise ValueError("HOLD_CHAT_UI_ANCHOR")
        text = text.replace(old, new, 1)
    candidate = text.encode("utf-8")
    if candidate == raw or any(old in text for old, _ in ANCHORS):
        raise ValueError("HOLD_CHAT_UI_UNCHANGED")
    return candidate


def candidate_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
