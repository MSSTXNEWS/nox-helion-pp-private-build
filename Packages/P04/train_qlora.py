#!/usr/bin/env python3
"""Fail-closed local QLoRA worker for NOX.

The worker never installs packages or downloads model weights. It requires a
locally pinned model snapshot, a consent manifest accepted by an external
rights verifier, SHA-bound train/holdout JSONL files, and a visible NVIDIA GPU.
It emits NOX-INSTALLER-EVENT-v3 NDJSON from real Transformers callbacks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_SCHEMA = "NOX-INSTALLER-EVENT-v3"
RECEIPT_SCHEMA = "NOX-QLORA-TRAINING-RECEIPT-v2"
DEFAULT_THERMAL_STOP_C = 83.0
PROFILES = {
    "ECO": {"max_steps": 20, "max_epochs": 1, "max_batch": 1, "max_seq": 1024, "grad_accum": 16, "save_steps": 5, "eval_steps": 5},
    "BALANCED": {"max_steps": 40, "max_epochs": 2, "max_batch": 2, "max_seq": 2048, "grad_accum": 8, "save_steps": 10, "eval_steps": 10},
    "INTENSIVE": {"max_steps": 80, "max_epochs": 3, "max_batch": 4, "max_seq": 4096, "grad_accum": 4, "save_steps": 10, "eval_steps": 10},
}
SECRET_RE = re.compile(r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential)\s*[:=]\s*[^\s,;]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha25¶»§q«^