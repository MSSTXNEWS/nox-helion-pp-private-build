"""NOX V16 owner #4 ONEHOST adapter around the ORIGINAL train_qlora.py.

Reuse: Hugging Face Transformers/PEFT/TRL in the existing worker. This module
never downloads weights, implements a trainer, or marks a GPU result accepted.
Only the authenticated native host supplies approved plans and exact receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Callable

HEX64 = re.compile(r"[0-9a-f]{64}\\Z", re.I)
RUN_ID = re.compile(r"[A-Za-z0-9._:-]{8,128}\\Z")
ARGS = frozenset({
    "--model", "--model-lock", "--model-revision", "--dataset-manifest",
    "--rights-verifier", "--train-jsonl", "--holdout-jsonl", "--output-dir",
    "--events-jsonl", "--run-id", "--task-id", "--stop-marker",
    "--pause-marker", "--resume-from-checkpoint", "--profile", "--max-steps",
    "--epochs", "--batch-size", "--learning-rate", "--max-seq-length",
    "--save-steps", "--eval-steps", "--gpu-index", "--thermal-stop-c",
})
REQUIRED = frozenset({
    "--model", "--model-lock", "--model-revision", "--dataset-manifest",
    "--rights-verifier", "--train-jsonl", "--holdout-jsonl", "--output-dir",
    "--events-jsonl", "--run-id", "--task-id", "--stop-marker",
})

class P04Hold(RuntimeError):
    pass

class P04Denied(PermissionError):
    pass

@dataclass(frozen=True)
class NativeQLoRAPlan:
    python_exe: Path
    worker_file: Path
    worker_sha256: str
    argv_pairs: tuple[str, ...]
    run_id: str


def _file(p: Path) -> Path:
    if not isinstance(p, Path) or not p.is_absolute() or not p.is_file():
        raise P04Hold("NATIVE_EXISTING_REGULAR_FILE_REQUIRED")
    if any(parent.is_symlink() for parent in (p, *p.parents)):
        raise P04Hold("NATIVE_REPARSE_PATH_REJECTED")
    return p.resolve(strict=True)


def _plan_args(plan: NativeQLoRAPlan) -> tuple[str, ...]:
    v = plan.argv_pairs
    if not isinstance(v, tuple) or len(v) % 2 or not 24 <= len(v) <= 48:
        raise P04Hold("NATIVE_QLORA_ARGUMENT_PAIRS_REQUIRED")
    pairs = list(zip(v[::2], v[1::2]))
    if any(type(k) is not str or type(val) is not str or k not in ARGS or not val
           or val.startswith("--") or "\x00" in val or len(val) > 4096
           for k, val in pairs):
        raise P04Hold("UNTRUSTED_QLORA_ARGUMENT")
    d = dict(pairs)
    if len(d) != len(pairs) or not REQUIRED.issubset(d):
        raise P04Hold("DUPLICATE_OR_MISSING_QLORA_ARGUMENT")
    if (not isinstance(plan.run_id, str) or not RUN_ID.fullmatch(plan.run_id)
            or d["--run-id"] != plan.run_id or not RUN_ID.fullmatch(d["--task-id"])):
        raise P04Hold("NATIVE_RUN_AND_TASK_ID_MISMATCH")
    if d.get("--profile", "BALANCED") not in ("ECO", "BALANCED", "MAX"):
        raise P04Hold("UNAPPROVED_GPU_PROFILE")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", d["--model-revision"]):
        raise P04Hold("IMMUTABLE_MODEL_REVISION_REQUIRED")
    return v

class P04OriginalTrainingPorts:
    """Register to existing PACK01 host only after owner native capability proof."""
    def __init__(self, *, select_plan: Callable, select_receipt: Callable,
                 permission: Callable, stop: Callable, launcher: Callable | None = None):
        if not all(callable(x) for x in (select_plan, select_receipt, permission, stop)):
            raise P04Hold("NATIVE_OWNER_CALLBACKS_REQUIRED")
        self._plan, self._receipt = select_plan, select_receipt
        self._permission, self._stop = permission, stop
        self._launch = launcher or self._native_launch
        self._active = None

    @staticmethod
    def _native_launch(argv: tuple[str, ...]):
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                shell=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def available(self) -> bool:
        return callable(self._plan) and callable(self._permission) and callable(self._stop)

    def start(self, session, payload: dict):
        if type(payload) is not dict or payload:
            raise P04Denied("NO_PAGE_SUPPLIED_TRAINING_ARGS")
        if self._stop() is not False or self._permission(session, "training.start") is not True:
            raise P04Denied("NATIVE_TRAINING_APPROVAL_REQUIRED")
        if self._active is not None and self._active.poll() is None:
            raise P04Hold("QLORA_ALREADY_RUNNING")
        plan = self._plan(session)
        if not isinstance(plan, NativeQLoRAPlan) or type(plan.worker_sha256) is not str or not HEX64.fullmatch(plan.worker_sha256):
            raise P04Hold("NATIVE_PINNED_QLORA_PLAN_REQUIRED")
        python_exe, worker = _file(plan.python_exe), _file(plan.worker_file)
        if worker.name != "train_qlora.py" or sha256(worker.read_bytes()).hexdigest() != plan.worker_sha256.lower():
            raise P04Hold("ORIGINAL_TRAINER_SHA_DRIFT")
        v = _plan_args(plan)
        if self._stop() is not False or self._permission(session, "training.start") is not True:
            raise P04Denied("NATIVE_TRAINING_CONSENT_REVOKED")
        process = self._launch((str(python_exe), str(worker), *v))
        if process is None or not callable(getattr(process, "poll", None)):
            raise P04Hold("NATIVE_TRAINER_PROCESS_NOT_PROVEN")
        if process.poll() is not None:
            raise P04Hold("ORIGINAL_TRAINER_EXITED_EARLY")
        self._active = process
        return {"status": "ORIGINAL_QLORA_PROCESS_STARTED_NOT_TRAINED", "run_id": plan.run_id, "accepted": False}

    def evaluate(self, session, payload: dict):
        if type(payload) is not dict or payload:
            raise P04Denied("NO_PAGE_SUPPLIED_RECEIPT_PATH")
        if self._stop() is not False or self._permission(session, "training.evaluate") is not True:
            raise P04Denied("NATIVE_EVALUATION_APPROVAL_REQUIRED")
        pair = self._receipt(session)
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise P04Hold("NATIVE_EVALUATION_RECEIPT_REQUIRED")
        path, digest = pair
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise P04Hold("NATIVE_RECEIPT_SHA_REQUIRED")
        f = _file(path)
        if f.stat().st_size > 65536:
            raise P04Hold("UNBOUNDED_RECEIPT")
        raw = f.read_bytes()
        if sha256(raw).hexdigest() != digest.lower():
            raise P04Hold("TRAINER_RECEIPT_SHA_DRIFT")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as e:
            raise P04Hold("INVALID_ORIGINAL_RECEIPT_JSON") from e
        if not isinstance(result, dict) or not isinstance(result.get("training"), dict):
            raise P04Hold("ORIGINAL_RECEIPT_SCHEMA_REQUIRED")
        item = result["training"]
        a, b = item.get("baseline_eval_loss"), item.get("adapter_eval_loss")
        verified_metrics = (type(a) in (float, int) and type(b) in (float, int)
                            and math.isfinite(a) and math.isfinite(b))
        if not verified_metrics:
            return {"status": "HOLD_NO_FINITE_EVALUATION", "accepted": False}
        return {"status": item.get("evaluation_status", "HOLD_UNVERIFIED"),
                "baseline_eval_loss": a, "adapter_eval_loss": b,
                "improved": b < a, "accepted": False}
