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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_reparse_ancestors(path: Path) -> None:
    """Fail closed on inherited symbolic links / Windows junctions.

    A native host still owns the trusted data root and must protect against
    filesystem replacement races; this is a preflight, not a handle sandbox.
    """
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("P04_PATH_ANCESTOR_UNREADABLE") from exc
        if (stat.S_ISLNK(info.st_mode) or
                (getattr(info, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise ValueError("P04_PATH_REPARSE_ANCESTOR")


def validate_training_limits(profile: dict[str, Any], max_steps: int,
                             epochs: float, save_steps: int, eval_steps: int) -> None:
    """Bound actual GPU work to the approved ECO/BALANCED/INTENSIVE budget."""
    if ((max_steps != -1 and not 1 <= max_steps <= profile["max_steps"])
            or not math.isfinite(epochs) or not 0 < epochs <= profile["max_epochs"]):
        raise ValueError("P04_TRAINING_PROFILE_BUDGET_EXCEEDED")
    # Very short operator-approved smoke runs may end before the periodic
    # save/eval interval; the trainer still performs its terminal evaluation
    # and explicit PAUSE/STOP forces a full-state save.
    if save_steps < 1 or eval_steps < 1:
        raise ValueError("P04_TRAINING_CHECKPOINT_EVAL_INTERVAL_INVALID")


def finite_metric(value: Any) -> float | None:
    """Keep non-finite or missing metrics out of completion receipts."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def sha256_tree(root: Path) -> str:
    """Hash a directory deterministically and reject symbolic links."""
    if root.is_symlink():
        raise ValueError("TREE_ROOT_NOT_REGULAR_DIRECTORY")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("TREE_ROOT_NOT_REGULAR_DIRECTORY")
    digest = hashlib.sha256()
    files = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for path in files:
        if path.is_symlink():
            raise ValueError("SYMLINK_IN_PINNED_TREE")
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(bytes.fromhex(sha256_file(path)))
    if not any(path.is_file() for path in files):
        raise ValueError("EMPTY_PINNED_TREE")
    return digest.hexdigest()


def write_training_receipt(output: Path, receipt: dict[str, Any]) -> tuple[str, Path]:
    """Preserve immutable per-run receipt before replacing the latest view.

    Based on the useful atomic receipt concept from candidate PR #6, while
    retaining the single real PEFT backend and v2 receipt schema from PR #7.
    No GPU or model weights are needed to verify this function.
    """
    payload = (json.dumps(receipt, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    archive_dir = output / "receipts"
    if archive_dir.is_symlink():
        raise ValueError("TRAIN_RECEIPT_ARCHIVE_SYMLINK")
    archive_dir.mkdir(exist_ok=True)
    archive = archive_dir / (digest + ".json")
    if archive.is_symlink():
        raise ValueError("TRAIN_RECEIPT_ARCHIVE_SYMLINK")
    if archive.exists():
        if not archive.is_file() or sha256_file(archive) != digest:
            raise ValueError("TRAIN_RECEIPT_ARCHIVE_COLLISION")
    else:
        try:
            with archive.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if not archive.is_file() or archive.is_symlink() or sha256_file(archive) != digest:
                raise ValueError("TRAIN_RECEIPT_ARCHIVE_COLLISION")
    latest = output / "training-receipt.json"
    if latest.is_symlink():
        raise ValueError("TRAIN_RECEIPT_LATEST_SYMLINK")
    fd, temporary = tempfile.mkstemp(prefix=".training-receipt-", suffix=".tmp", dir=output)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, latest)
        try:
            directory_fd = os.open(output, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if sha256_file(latest) != digest:
        raise ValueError("TRAIN_RECEIPT_WRITE_VERIFICATION_FAILED")
    return digest, latest


def read_object(path: Path) -> dict[str, Any]:
    """Parse authorization and resume JSON with unambiguous, finite semantics.

    These bytes are also interpreted by rights verifiers or future recovery
    tooling; duplicate keys and NaN/Infinity must not produce split decisions.
    """
    if path.is_symlink() or not path.is_file():
        raise ValueError("INPUT_NOT_REGULAR_FILE")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("INPUT_JSON_DUPLICATE_KEY")
            obj[key] = value
        return obj

    def reject_constant(_token: str) -> None:
        raise ValueError("INPUT_JSON_NONFINITE")

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("INPUT_JSON_NONFINITE")
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
            parse_constant=reject_constant, parse_float=finite_float,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("INPUT_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("EXPECTED_JSON_OBJECT")
    return value


def verify_manifest(manifest_path: Path, train_path: Path, holdout_path: Path,
                    verifier: Path) -> dict[str, Any]:
    manifest = read_object(manifest_path)
    required = {
        "schema": "nox-dataset-consent-v1",
        "rights_status": "APPROVED",
        "consent_status": "GRANTED",
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise ValueError("DATASET_" + key.upper() + "_NOT_APPROVED")
    for key in ("dataset_id", "dataset_revision", "license_id", "owner_approval_id"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError("DATASET_" + key.upper() + "_MISSING")
    for label, path in (("train", train_path), ("holdout", holdout_path)):
        expected = manifest.get(label + "_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ValueError("DATASET_" + label.upper() + "_SHA256_MISSING")
        if sha256_file(path).lower() != expected.lower():
            raise ValueError("DATASET_" + label.upper() + "_SHA256_MISMATCH")
    if manifest["train_sha256"].lower() == manifest["holdout_sha256"].lower():
        raise ValueError("TRAIN_AND_HOLDOUT_MUST_DIFFER")
    if verifier.is_symlink() or not verifier.is_file():
        raise ValueError("RIGHTS_VERIFIER_NOT_REGULAR_FILE")
    manifest_sha = sha256_file(manifest_path)
    # The verifier is an explicit local executable, not a shell command.
    result = subprocess.run(
        [str(verifier.resolve(strict=True)), "--manifest", str(manifest_path.resolve(strict=True)),
         "--intent", "training", "--manifest-sha256", manifest_sha],
        check=False, capture_output=True, text=True, timeout=30, shell=False,
    )
    if result.returncode != 0:
        raise ValueError("RIGHTS_VERIFIER_REJECTED_MANIFEST")
    try:
        attestation = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("RIGHTS_VERIFIER_INVALID_RESPONSE") from exc
    # Bind the verifier's decision to every authorization-bearing manifest
    # field and both exact payload digests. A valid status for a dataset ID
    # alone is insufficient: it could otherwise be replayed across revisions,
    # licenses, approvals, or changed train/holdout files.
    attested_fields = {
        "schema": "nox-rights-attestation-v1",
        "status": "VERIFIED",
        "manifest_sha256": manifest_sha,
        "dataset_id": manifest["dataset_id"],
        "dataset_revision": manifest["dataset_revision"],
        "license_id": manifest["license_id"],
        "owner_approval_id": manifest["owner_approval_id"],
        "train_sha256": manifest["train_sha256"].lower(),
        "holdout_sha256": manifest["holdout_sha256"].lower(),
        "intent": "training",
    }
    if (not isinstance(attestation, dict)
            or any(not isinstance(attestation.get(key), str)
                   or attestation[key].lower() != expected.lower()
                   for key, expected in attested_fields.items())
            or not isinstance(attestation.get("attestation_id"), str)
            or not attestation["attestation_id"].strip()):
        raise ValueError("RIGHTS_VERIFIER_ATTESTATION_MISMATCH")
    manifest["_rights_attestation_id"] = attestation["attestation_id"].strip()
    manifest["_rights_attestation_sha256"] = hashlib.sha256(
        json.dumps(attestation, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest


def verify_model_lock(lock_path: Path, model_path: Path, expected_revision: str) -> dict[str, Any]:
    lock = read_object(lock_path)
    if lock.get("schema") != "nox-model-lock-v1":
        raise ValueError("MODEL_LOCK_SCHEMA_UNSUPPORTED")
    if lock.get("license_status") != "APPROVED" or not lock.get("owner_approval_id"):
        raise ValueError("MODEL_LICENSE_OR_OWNER_APPROVAL_MISSING")
    if lock.get("revision") != expected_revision or not re.fullmatch(r"[0-9a-fA-F]{40}", expected_revision):
        raise ValueError("MODEL_REVISION_LOCK_MISMATCH")
    if lock.get("model_id") is None or not isinstance(lock["model_id"], str):
        raise ValueError("MODEL_ID_MISSING")
    actual_tree = sha256_tree(model_path)
    expected_tree = lock.get("snapshot_sha256")
    if not isinstance(expected_tree, str) or actual_tree.lower() != expected_tree.lower():
        raise ValueError("MODEL_SNAPSHOT_SHA256_MISMATCH")
    return lock


MAX_JSONL_LINE_CHARACTERS = 1_048_576


def parse_dataset_record(line: str, label: str, number: int) -> dict[str, Any]:
    """Fail closed on ambiguous JSONL keys and non-finite numeric literals.

    Python's permissive json.loads accepts repeated keys and NaN/Infinity.
    Other loaders may interpret those same bytes differently. Reject before
    hashing split identities or handing any record to a GPU trainer.
    """
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"{label}_JSON_DUPLICATE_KEY_{number}")
            obj[key] = value
        return obj

    def reject_constant(_value: str) -> None:
        raise ValueError(f"{label}_JSON_NONFINITE_{number}")

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(f"{label}_JSON_NONFINITE_{number}")
        return value

    try:
        row = json.loads(line, object_pairs_hook=unique_pairs,
                         parse_constant=reject_constant, parse_float=finite_float)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}_INVALID_JSONL_{number}") from exc
    if not isinstance(row, dict):
        raise ValueError(f"{label}_ROW_NOT_OBJECT_{number}")
    # SFTTrainer may prefer conversational/prompt-completion columns over
    # `text`. Accept exactly one supervised representation per record so
    # the leakage fingerprint cannot describe different data than the GPU sees.
    if ("text" in row and "messages" in row) or "prompt" in row or "completion" in row:
        raise ValueError(f"{label}_AMBIGUOUS_TRAINING_COLUMNS_{number}")
    return row


def validate_jsonl(path: Path, label: str) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if len(line) > MAX_JSONL_LINE_CHARACTERS:
                raise ValueError(f"{label}_LINE_TOO_LONG_{number}")
            if not line.strip():
                continue
            row = parse_dataset_record(line, label, number)
            if isinstance(row.get("text"), str) and row["text"].strip():
                count += 1
                if count > MAX_DATASET_LEAKAGE_SCAN_ROWS:
                    raise ValueError(f"{label}_RECORD_LIMIT_EXCEEDED")
                continue
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"{label}_ROW_NEEDS_TEXT_OR_MESSAGES_{number}")
            valid_assistant = False
            for item in messages:
                if (not isinstance(item, dict) or item.get("role") not in {"system", "user", "assistant"}
                        or not isinstance(item.get("content"), str)):
                    raise ValueError(f"{label}_INVALID_MESSAGE_{number}")
                valid_assistant |= item["role"] == "assistant" and bool(item["content"].strip())
            if not valid_assistant:
                raise ValueError(f"{label}_NO_ASSISTANT_TARGET_{number}")
            count += 1
            if count > MAX_DATASET_LEAKAGE_SCAN_ROWS:
                raise ValueError(f"{label}_RECORD_LIMIT_EXCEEDED")
    if count == 0:
        raise ValueError(f"{label}_EMPTY")
    return count



MAX_DATASET_LEAKAGE_SCAN_ROWS = 500_000


def validate_holdout_separation(train_path: Path, holdout_path: Path) -> tuple[int, int]:
    """Reject exact training/holdout examples before accessing CUDA.

    The train and holdout SHA-256 manifest checks protect file identity, not
    against duplicate samples hidden in differently ordered files. Scan only
    validated local JSONL files, bounded to avoid untrusted input memory growth.
    """
    def payload_digest(row: dict[str, Any]) -> bytes:
        value = row.get("text")
        if isinstance(value, str) and value.strip():
            payload = value.strip()
        else:
            # The model-visible dialogue is role/content; donor provenance
            # and annotation keys must not conceal the same supervised sample
            # across train/holdout or inflate training with duplicate examples.
            payload = json.dumps(
                [{"role": message["role"], "content": message["content"]}
                 for message in row["messages"]],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).digest()

    def records(path: Path, label: str):
        count = 0
        with path.open("r", encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                count += 1
                if count > MAX_DATASET_LEAKAGE_SCAN_ROWS:
                    raise ValueError(label + "_LEAKAGE_SCAN_LIMIT_EXCEEDED")
                if len(line) > MAX_JSONL_LINE_CHARACTERS:
                    raise ValueError(label + "_LEAKAGE_SCAN_LINE_TOO_LONG")
                yield payload_digest(parse_dataset_record(line, label, number))
        if count == 0:
            raise ValueError(label + "_EMPTY")

    # Count physical examples, not unique hashes; duplicate records inflate
    # optimizer/evaluation statistics and can mask a corrupted holdout.
    train_digests = set()
    train_rows = 0
    for digest in records(train_path, "TRAIN"):
        train_rows += 1
        if digest in train_digests:
            raise ValueError("DATASET_TRAIN_DUPLICATE_EXAMPLE")
        train_digests.add(digest)
    holdout_digests = set()
    holdout_rows = 0
    for digest in records(holdout_path, "HOLDOUT"):
        holdout_rows += 1
        if digest in train_digests:
            raise ValueError("DATASET_TRAIN_HOLDOUT_EXAMPLE_OVERLAP")
        if digest in holdout_digests:
            raise ValueError("DATASET_HOLDOUT_DUPLICATE_EXAMPLE")
        holdout_digests.add(digest)
    return train_rows, holdout_rows


def verify_dataset_unchanged(manifest: dict[str, Any], train_path: Path, holdout_path: Path) -> None:
    """Reattest the identical approved bytes immediately before opening the dataset."""
    for name, path in (("train", train_path), ("holdout", holdout_path)):
        digest = manifest.get(name + "_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("DATASET_" + name.upper() + "_SHA256_MISSING")
        if path.is_symlink() or not path.is_file() or sha256_file(path).casefold() != digest.casefold():
            raise ValueError("DATASET_" + name.upper() + "_MODIFIED_AFTER_PREFLIGHT")


def nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if exe:
        return exe
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def gpu_inventory(exe: str) -> list[dict[str, str]]:
    result = subprocess.run(
        [exe, "--query-gpu=index,name,uuid,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10, shell=False, check=False,
    )
    if result.returncode:
        raise RuntimeError("NVIDIA_GPU_INVENTORY_FAILED")
    rows = []
    for line in result.stdout.splitlines():
        fields = [part.strip() for part in line.split(",", 3)]
        if len(fields) == 4 and fields[0].isdigit() and fields[2].startswith("GPU-"):
            rows.append({"index": fields[0], "name": fields[1], "uuid": fields[2], "memory_total_mib": fields[3]})
    if not rows:
        raise RuntimeError("NO_NVIDIA_GPU_FOUND")
    return rows


def gpu_temperature(exe: str, gpu_uuid: str) -> float | None:
    try:
        result = subprocess.run(
            [exe, "--id=" + gpu_uuid, "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, shell=False, check=False,
        )
        if result.returncode:
            return None
        value = float(result.stdout.strip().splitlines()[0])
        return value if 0 <= value <= 150 else None
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def gpu_vram_headroom(exe: str, gpu_uuid: str, profile: str) -> dict[str, int]:
    """Read real free VRAM before CUDA; reserve memory for the Windows UI.

    This is a start gate, NOT a claim that utilization or memory is capped.
    Never infer free VRAM from total capacity or a synthetic sensor value.
    """
    if profile not in PROFILES or not re.fullmatch(r"GPU-[A-Za-z0-9-]{4,128}", gpu_uuid):
        raise ValueError("GPU_HEADROOM_IDENTITY_INVALID")
    try:
        result = subprocess.run(
            [exe, "--id=" + gpu_uuid, "--query-gpu=memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("GPU_VRAM_TELEMETRY_UNAVAILABLE") from exc
    if result.returncode:
        raise RuntimeError("GPU_VRAM_TELEMETRY_UNAVAILABLE")
    fields = result.stdout.strip().splitlines()
    if len(fields) != 1:
        raise RuntimeError("GPU_VRAM_TELEMETRY_INVALID")
    numbers = [part.strip() for part in fields[0].split(",")]
    if len(numbers) != 2 or any(re.fullmatch(r"[0-9]{1,9}", x) is None for x in numbers):
        raise RuntimeError("GPU_VRAM_TELEMETRY_INVALID")
    free_mib, total_mib = map(int, numbers)
    if not 1 <= total_mib <= 1024 * 1024 or not 0 <= free_mib <= total_mib:
        raise RuntimeError("GPU_VRAM_TELEMETRY_INVALID")
    reserve_pct = {"ECO": 30, "BALANCED": 20, "INTENSIVE": 20}[profile]
    reserve_mib = max(1024, (total_mib * reserve_pct + 99) // 100)
    if free_mib < reserve_mib + 1024:
        raise RuntimeError("GPU_VRAM_INSUFFICIENT_GUI_HEADROOM")
    return {"free_mib": free_mib, "total_mib": total_mib,
            "gui_reserve_mib": reserve_mib}


class EventWriter:
    """Append-only v3 events with fail-closed run identity and resume sequence."""

    def __init__(self, path: Path, run_id: str, task_id: str):
        if (not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", run_id)
                or not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", task_id)):
            raise ValueError("EVENT_RUN_TASK_ID_INVALID")
        self.path, self.run_id, self.task_id = path, run_id, task_id
        if self.path.parent.is_symlink():
            raise ValueError("EVENT_LOG_PARENT_SYMLINK")
        reject_reparse_ancestors(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        reject_reparse_ancestors(self.path)
        self.lock = threading.Lock()
        self.sequence = 0
        if self.path.is_symlink():
            raise ValueError("EVENT_LOG_SYMLINK")
        if self.path.exists():
            if not self.path.is_file():
                raise ValueError("EVENT_LOG_NOT_REGULAR_FILE")
            size = self.path.stat().st_size
            if size:
                with self.path.open("rb") as stream:
                    stream.seek(max(size - 8192, 0))
                    tail = stream.read(8192)
                if not tail.endswith(b"\n"):
                    raise ValueError("EVENT_LOG_INCOMPLETE_TAIL")
                last = tail.rstrip(b"\n").rsplit(b"\n", 1)[-1]
                if len(last) > 4096:
                    raise ValueError("EVENT_LOG_LAST_LINE_TOO_LONG")
                try:
                    previous = json.loads(last)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("EVENT_LOG_LAST_EVENT_INVALID") from exc
                if (not isinstance(previous, dict)
                        or previous.get("schema") != EVENT_SCHEMA
                        or previous.get("run_id") != run_id
                        or previous.get("task_id") != task_id
                        or type(previous.get("event_sequence")) is not int
                        or previous["event_sequence"] < 1):
                    raise ValueError("EVENT_LOG_RUN_IDENTITY_MISMATCH")
                self.sequence = previous["event_sequence"]

    @staticmethod
    def clean(message: str) -> str:
        message = SECRET_RE.sub(r"\1=[REDACTED]", str(message))
        message = re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", message)
        return message[:240]

    def emit(self, event_type: str, state: str, action: str, message: str,
             numerator: int | None = None, denominator: int | None = None,
             metric_name: str | None = None, metric_value: float | None = None) -> None:
        if any(value is not None and (type(value) is not int or value < 0)
               for value in (numerator, denominator)):
            raise ValueError("EVENT_PROGRESS_INVALID")
        if metric_value is not None and finite_metric(metric_value) is None:
            raise ValueError("EVENT_METRIC_NOT_FINITE")
        with self.lock:
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise ValueError("EVENT_LOG_SYMLINK")
            reject_reparse_ancestors(self.path)
            next_sequence = self.sequence + 1
            event = {
                "schema": EVENT_SCHEMA, "run_id": self.run_id, "event_id": uuid.uuid4().hex,
                "event_sequence": next_sequence, "event_type": event_type, "task_id": self.task_id,
                "package_id": "P04", "action_id": action, "timestamp_utc": utc_now(),
                "state": state, "source": "P04.QLoRA", "message": self.clean(message),
                "numerator": numerator, "denominator": denominator, "evidence_verified": False,
                "metric_name": metric_name, "metric_value": metric_value,
            }
            payload = (json.dumps(event, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")) + "\n").encode("utf-8")
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            with os.fdopen(fd, "ab") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.sequence = next_sequence


def validated_checkpoint(checkpoint_dir: Path, selected: Path) -> tuple[int, str]:
    if selected.is_symlink() or not selected.is_dir():
        raise ValueError("RESUME_CHECKPOINT_NOT_REGULAR_DIRECTORY")
    root = checkpoint_dir.resolve(strict=True)
    real = selected.resolve(strict=True)
    if real.parent != root or not re.fullmatch(r"checkpoint-(\d+)", real.name):
        raise ValueError("RESUME_CHECKPOINT_OUTSIDE_RUN")
    state_path = real / "trainer_state.json"
    if state_path.is_symlink() or not state_path.is_file() or state_path.stat().st_size == 0:
        raise ValueError("RESUME_CHECKPOINT_TRAINER_STATE_INVALID")
    state = read_object(state_path)
    step = int(real.name.split("-")[-1])
    if type(state.get("global_step")) is not int or state["global_step"] != step:
        raise ValueError("RESUME_CHECKPOINT_STEP_MISMATCH")
    model_files = ("adapter_model.safetensors", "adapter_model.bin", "model.safetensors", "pytorch_model.bin")
    if not any((real / name).is_file() and not (real / name).is_symlink()
               and (real / name).stat().st_size > 0 for name in model_files):
        raise ValueError("RESUME_CHECKPOINT_MODEL_MISSING")
    for name in ("optimizer.pt", "scheduler.pt"):
        if not (real / name).is_file() or (real / name).stat().st_size == 0:
            raise ValueError("RESUME_CHECKPOINT_STATE_MISSING")
    if any(item.is_symlink() for item in real.rglob("*")):
        raise ValueError("RESUME_CHECKPOINT_SYMLINK_IN_TREE")
    rng = list(real.glob("rng_state*.pth"))
    if not rng or any(not path.is_file() or path.is_symlink() or path.stat().st_size == 0 for path in rng):
        raise ValueError("RESUME_CHECKPOINT_RNG_MISSING")
    return step, sha256_tree(real)


def acquire_gpu_lock(lock_path: Path) -> int:
    reject_reparse_ancestors(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    reject_reparse_ancestors(lock_path)
    try:
        return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("GPU_TRAINING_QUEUE_BUSY") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path, help="already-installed local model snapshot")
    parser.add_argument("--model-lock", required=True, type=Path)
    parser.add_argument("--model-revision", required=True, help="immutable 40-character model revision")
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--rights-verifier", required=True, type=Path, help="local verifier executable; no shell")
    parser.add_argument("--train-jsonl", required=True, type=Path)
    parser.add_argument("--holdout-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--events-jsonl", required=True, type=Path)
    parser.add_argument("--run-id", default=uuid.uuid4().hex)
    parser.add_argument("--task-id", default="P04-" + uuid.uuid4().hex)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="BALANCED")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--max-steps", type=int)
    group.add_argument("--epochs", type=float)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int)
    parser.add_argument("--save-steps", type=int)
    parser.add_argument("--eval-steps", type=int)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--thermal-stop-c", type=float, default=DEFAULT_THERMAL_STOP_C)
    parser.add_argument("--stop-marker", required=True, type=Path)
    parser.add_argument("--pause-marker", type=Path)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", args.run_id) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", args.task_id):
        parser.error("run-id/task-id format invalid")
    profile = PROFILES[args.profile]
    max_steps = args.max_steps if args.max_steps is not None else (-1 if args.epochs is not None else profile["max_steps"])
    epochs = args.epochs if args.epochs is not None else profile["max_epochs"]
    batch_size = args.batch_size
    max_seq = args.max_seq_length or profile["max_seq"]
    save_steps = args.save_steps or profile["save_steps"]
    eval_steps = args.eval_steps or profile["eval_steps"]
    try:
        validate_training_limits(profile, max_steps, epochs, save_steps, eval_steps)
    except ValueError as exc:
        parser.error(str(exc))
    if batch_size < 1 or batch_size > profile["max_batch"]:
        parser.error("batch-size exceeds profile")
    if not (1e-6 <= args.learning_rate <= 1e-3 and 128 <= max_seq <= profile["max_seq"]):
        parser.error("learning-rate or max-seq-length outside profile")
    if save_steps < 1 or eval_steps < 1 or args.gpu_index < 0 or not 50 <= args.thermal_stop_c <= 90:
        parser.error("invalid save/eval/GPU/thermal setting")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.model_revision):
        parser.error("model-revision must be an immutable 40-character revision")

    # Check caller-supplied lexical ancestors BEFORE resolve(strict=True)
    # can silently erase symlink/junction evidence. Native host still owns
    # trusted-root authorization and replacement-race protections.
    for candidate in (args.model, args.model_lock, args.dataset_manifest,
                      args.rights_verifier, args.train_jsonl, args.holdout_jsonl,
                      args.output_dir, args.events_jsonl, args.stop_marker,
                      args.pause_marker, args.resume_from_checkpoint):
        if candidate is not None:
            reject_reparse_ancestors(candidate.absolute())
    events = EventWriter(args.events_jsonl, args.run_id, args.task_id)
    lock_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NOX" / "P04" / "gpu-training.lock"
    lock_fd = None
    status = "ERROR"
    try:
        for path in (args.dataset_manifest, args.train_jsonl, args.holdout_jsonl, args.model_lock):
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_file():
                raise ValueError("INPUT_NOT_REGULAR_FILE")
        model_path = args.model.resolve(strict=True)
        if args.model.is_symlink() or not model_path.is_dir():
            raise ValueError("MODEL_SNAPSHOT_NOT_REGULAR_DIRECTORY")
        if args.stop_marker.exists():
            raise ValueError("STOP_MARKER_ALREADY_PRESENT")
        if args.pause_marker and args.pause_marker.exists():
            raise ValueError("PAUSE_MARKER_ALREADY_PRESENT")
        manifest_path = args.dataset_manifest.resolve(strict=True)
        train_path = args.train_jsonl.resolve(strict=True)
        holdout_path = args.holdout_jsonl.resolve(strict=True)
        manifest = verify_manifest(manifest_path, train_path, holdout_path, args.rights_verifier.resolve(strict=True))
        model_lock = verify_model_lock(args.model_lock.resolve(strict=True), model_path, args.model_revision)
        train_records = validate_jsonl(train_path, "TRAIN")
        holdout_records = validate_jsonl(holdout_path, "HOLDOUT")
        validate_holdout_separation(train_path, holdout_path)

        exe = nvidia_smi()
        if not exe:
            raise RuntimeError("NVIDIA_GPU_TELEMETRY_UNAVAILABLE")
        devices = gpu_inventory(exe)
        chosen = next((item for item in devices if int(item["index"]) == args.gpu_index), None)
        if chosen is None:
            raise RuntimeError("SELECTED_GPU_INDEX_NOT_FOUND")
        temp = gpu_temperature(exe, chosen["uuid"])
        if temp is None:
            raise RuntimeError("GPU_TEMPERATURE_UNAVAILABLE")
        if temp >= args.thermal_stop_c:
            raise RuntimeError("GPU_TEMPERATURE_LIMIT_EXCEEDED")
        vram_headroom = gpu_vram_headroom(exe, chosen["uuid"], args.profile)
        lock_fd = acquire_gpu_lock(lock_path)
        os.write(lock_fd, (args.run_id + "\n").encode())
        os.fsync(lock_fd)

        params = {
            "run_id": args.run_id, "task_id": args.task_id,
            "model_id": model_lock["model_id"], "model_revision": args.model_revision,
            "model_snapshot_sha256": model_lock["snapshot_sha256"].lower(),
            "model_lock_sha256": sha256_file(args.model_lock.resolve(strict=True)),
            "dataset_id": manifest["dataset_id"], "dataset_revision": manifest["dataset_revision"],
            "dataset_manifest_sha256": sha256_file(manifest_path),
            "license_id": manifest["license_id"], "owner_approval_id": manifest["owner_approval_id"],
            "train_sha256": manifest["train_sha256"].lower(), "holdout_sha256": manifest["holdout_sha256"].lower(),
            "rights_attestation_id": manifest["_rights_attestation_id"],
            "rights_attestation_sha256": manifest["_rights_attestation_sha256"],
            "profile": args.profile, "max_steps": max_steps, "epochs": args.epochs,
            "batch_size": batch_size, "learning_rate": args.learning_rate, "max_seq_length": max_seq,
            "save_steps": save_steps, "eval_steps": eval_steps,
        }
        output = args.output_dir.resolve()
        checkpoint_dir = output / "checkpoints"
        run_lock = output / "training-run.json"
        resume = None
        if args.resume_from_checkpoint is not None:
            if output.is_symlink() or not output.is_dir() or checkpoint_dir.is_symlink() or not checkpoint_dir.is_dir():
                raise ValueError("RESUME_OUTPUT_DIRECTORY_INVALID")
            if run_lock.is_symlink() or not run_lock.is_file() or read_object(run_lock) != params:
                raise ValueError("RESUME_RUN_IDENTITY_MISMATCH")
            selected = args.resume_from_checkpoint
            step, resume_sha = validated_checkpoint(checkpoint_dir, selected)
            prior_receipt_path = output / "training-receipt.json"
            if prior_receipt_path.is_symlink() or not prior_receipt_path.is_file():
                raise ValueError("RESUME_RECEIPT_MISSING")
            prior_receipt = read_object(prior_receipt_path)
            prior_model = prior_receipt.get("model", {})
            prior_dataset = prior_receipt.get("dataset", {})
            prior_checkpoint = prior_receipt.get("checkpoint", {})
            selected_relative = selected.resolve(strict=True).relative_to(output).as_posix()
            if (prior_receipt.get("schema") != RECEIPT_SCHEMA or prior_receipt.get("run_id") != args.run_id
                    or prior_receipt.get("status") != "PAUSED"):
                raise ValueError("RESUME_REQUIRES_MATCHING_PAUSED_RECEIPT")
            if (prior_model.get("id") != model_lock["model_id"]
                    or prior_model.get("revision") != args.model_revision
                    or prior_model.get("snapshot_sha256", "").casefold() != model_lock["snapshot_sha256"].casefold()):
                raise ValueError("RESUME_RECEIPT_MODEL_MISMATCH")
            expected_dataset = {
                "id": manifest["dataset_id"], "revision": manifest["dataset_revision"],
                "license_id": manifest["license_id"], "owner_approval_id": manifest["owner_approval_id"],
                "rights_attestation_id": manifest["_rights_attestation_id"],
                "rights_attestation_sha256": manifest["_rights_attestation_sha256"],
                "train_sha256": manifest["train_sha256"].lower(),
                "holdout_sha256": manifest["holdout_sha256"].lower(),
            }
            if any(prior_dataset.get(key) != expected for key, expected in expected_dataset.items()):
                raise ValueError("RESUME_RECEIPT_DATASET_MISMATCH")
            if (prior_checkpoint.get("status") != "HASHED"
                    or prior_checkpoint.get("path") != selected_relative
                    or prior_checkpoint.get("tree_sha256", "").casefold() != resume_sha.casefold()):
                raise ValueError("RESUME_RECEIPT_CHECKPOINT_MISMATCH")
            resume = str(selected.resolve(strict=True))
        else:
            output.mkdir(parents=True, exist_ok=False)
            checkpoint_dir.mkdir()
            with run_lock.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(params, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            step, resume_sha = 0, None

        # Bind CUDA visibility before importing torch; the selected UUID is stable
        # even when Windows/CUDA enumeration order differs from nvidia-smi.
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        os.environ["CUDA_VISIBLE_DEVICES"] = chosen["uuid"]
        # Import expensive libraries only after rights/model/GPU preflight.
        import torch
        import transformers
        import peft
        import trl
        import accelerate
        from datasets import load_dataset
        from peft import LoraConfig, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainerCallback
        from trl import SFTConfig, SFTTrainer

        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("SELECTED_NVIDIA_GPU_NOT_VISIBLE_TO_CUDA")
        tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        bf16 = bool(torch.cuda.is_bf16_supported())
        dtype = torch.bfloat16 if bf16 else torch.float16
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
        verify_dataset_unchanged(manifest, train_path, holdout_path)
        train_dataset = load_dataset("json", data_files=str(train_path), split="train")
        eval_dataset = load_dataset("json", data_files=str(holdout_path), split="train")
        # Preserve approved source identity across dataset loading as well as before it.
        verify_dataset_unchanged(manifest, train_path, holdout_path)
        schedule = "epoch" if args.epochs is not None else "steps"
        training_args = SFTConfig(
            output_dir=str(checkpoint_dir), max_steps=max_steps, num_train_epochs=epochs,
            per_device_train_batch_size=batch_size, per_device_eval_batch_size=1,
            gradient_accumulation_steps=profile["grad_accum"], learning_rate=args.learning_rate,
            logging_steps=1, save_strategy=schedule, save_steps=save_steps, save_total_limit=3,
            eval_strategy=schedule, eval_steps=eval_steps, bf16=bf16, fp16=not bf16,
            gradient_checkpointing=True, report_to=[], max_length=max_seq,
            dataset_num_proc=1, disable_tqdm=True, save_only_model=False,
        )
        monitor = {"last_check": 0.0, "temperature": temp, "thermal_reason": None,
                   "resource_reason": None, "vram_free_mib": vram_headroom["free_mib"],
                   "stop": False, "pause": False, "train_loss": None, "eval_loss": None}
        class Callback(TrainerCallback):
            def on_log(self, args_, state, control, logs=None, **kwargs):
                logs = logs or {}
                train_metric = finite_metric(logs.get("loss"))
                if train_metric is not None:
                    monitor["train_loss"] = train_metric
                    events.emit("training.step", "RUNNING", "train_loss",
                                f"train_loss={monitor['train_loss']:.8g}",
                                int(state.global_step), int(state.max_steps),
                                "train_loss", monitor["train_loss"])
                eval_metric = finite_metric(logs.get("eval_loss"))
                if eval_metric is not None:
                    monitor["eval_loss"] = eval_metric
                    events.emit("training.step", "RUNNING", "validation_loss",
                                f"eval_loss={monitor['eval_loss']:.8g}",
                                int(state.global_step), int(state.max_steps),
                                "validation_loss", monitor["eval_loss"])
                return control
            def on_step_end(self, args_, state, control, **kwargs):
                events.emit("training.step", "RUNNING", "optimizer_step", "Trainer optimizer step completed.",
                            int(state.global_step), int(state.max_steps))
                now = __import__("time").monotonic()
                if now - monitor["last_check"] >= 5:
                    monitor["last_check"] = now
                    measured = gpu_temperature(exe, chosen["uuid"])
                    monitor["temperature"] = measured
                    if measured is None or measured >= args.thermal_stop_c:
                        monitor["thermal_reason"] = "GPU_TEMPERATURE_UNAVAILABLE" if measured is None else "GPU_TEMPERATURE_LIMIT_EXCEEDED"
                        control.should_save = True
                        control.should_training_stop = True
                        events.emit("task.progress", "HOLD", "gpu_thermal_stop", monitor["thermal_reason"])
                        return control
                    try:
                        current_vram = gpu_vram_headroom(exe, chosen["uuid"], args.profile)
                        monitor["vram_free_mib"] = current_vram["free_mib"]
                    except RuntimeError as exc:
                        monitor["resource_reason"] = str(exc)
                        control.should_save = True
                        control.should_training_stop = True
                        events.emit("task.progress", "HOLD", "gpu_vram_stop", monitor["resource_reason"])
                        return control
                if args.stop_marker.exists():
                    monitor["stop"] = True
                    control.should_save = True
                    control.should_training_stop = True
                elif args.pause_marker and args.pause_marker.exists():
                    monitor["pause"] = True
                    control.should_save = True
                    control.should_training_stop = True
                return control
            def on_save(self, args_, state, control, **kwargs):
                events.emit("checkpoint.saved", "RUNNING", "checkpoint_saved",
                            "Trainer reported a checkpoint save; full-state integrity is verified separately.",
                            int(state.global_step), int(state.max_steps))
                return control

        # Capture a genuine base holdout baseline before attaching LoRA.
        baseline_model = AutoModelForCausalLM.from_pretrained(
            str(model_path), local_files_only=True, trust_remote_code=False,
            quantization_config=quant, device_map={"": 0},
        )
        baseline_trainer = SFTTrainer(model=baseline_model, args=training_args, eval_dataset=eval_dataset,
                                      processing_class=tokenizer)
        baseline = baseline_trainer.evaluate()
        del baseline_trainer, baseline_model
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path), local_files_only=True, trust_remote_code=False,
            quantization_config=quant, device_map={"": 0},
        )
        model = prepare_model_for_kbit_training(model)
        model.config.use_cache = False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        lora = LoraConfig(
            r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        )
        trainer = SFTTrainer(model=model, args=training_args, train_dataset=train_dataset,
                             eval_dataset=eval_dataset, processing_class=tokenizer,
                             peft_config=lora, callbacks=[Callback()])
        events.emit("task.started", "RUNNING", "training_start",
                    "Consented QLoRA run passed manifest, model, and GPU preflight.",
                    0, int(training_args.max_steps) if int(training_args.max_steps) > 0 else None)
        result = trainer.train(resume_from_checkpoint=resume)
        global_step = int(trainer.state.global_step)
        total_steps = int(trainer.state.max_steps)
        if monitor["thermal_reason"] or monitor["resource_reason"]:
            status = "HOLD"
        elif monitor["stop"] or args.stop_marker.exists():
            status = "STOPPED"
        elif monitor["pause"]:
            status = "PAUSED"
        else:
            status = "COMPLETED"
        adapter_dir = output / "adapter"
        trainer.save_model(str(adapter_dir))
        (adapter_dir / "adapter-base.json").write_text(
            json.dumps({"model_id": model_lock["model_id"], "model_revision": args.model_revision,
                        "model_snapshot_sha256": model_lock["snapshot_sha256"].lower(),
                        "quantization": "4-bit NF4 QLoRA"}, sort_keys=True) + "\n", encoding="utf-8")
        del trainer, model
        gc.collect()
        torch.cuda.empty_cache()

        final_eval = {}
        if status == "COMPLETED":
            now_temp = gpu_temperature(exe, chosen["uuid"])
            if now_temp is None or now_temp >= args.thermal_stop_c:
                status = "HOLD"
                monitor["thermal_reason"] = "GPU_TEMPERATURE_UNAVAILABLE" if now_temp is None else "GPU_TEMPERATURE_LIMIT_EXCEEDED"
            else:
                from peft import PeftModel
                tuned = AutoModelForCausalLM.from_pretrained(
                    str(model_path), local_files_only=True, trust_remote_code=False,
                    quantization_config=quant, device_map={"": 0})
                tuned = PeftModel.from_pretrained(tuned, str(adapter_dir), is_trainable=False)
                evaluator = SFTTrainer(model=tuned, args=training_args, eval_dataset=eval_dataset,
                                       processing_class=tokenizer)
                final_eval = evaluator.evaluate()
                del evaluator, tuned
                gc.collect()
                torch.cuda.empty_cache()

        if args.pause_marker and monitor["pause"]:
            args.pause_marker.unlink(missing_ok=True)
        train_loss = finite_metric(result.training_loss)
        baseline_eval_loss = finite_metric(baseline.get("eval_loss"))
        adapter_eval_loss = finite_metric(final_eval.get("eval_loss"))
        evaluation_status = (
            "HOLD_MISSING_OR_NONFINITE" if baseline_eval_loss is None or adapter_eval_loss is None
            else "VALID" if adapter_eval_loss < baseline_eval_loss
            else "HOLD_NO_IMPROVEMENT"
        )
        if status == "COMPLETED" and (train_loss is None or evaluation_status != "VALID"):
            status = "HOLD"
        checkpoint_info = None
        candidates = sorted(checkpoint_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
        latest = candidates[-1] if candidates else None
        if latest is not None:
            step, tree_sha = validated_checkpoint(checkpoint_dir, latest)
            checkpoint_info = {"status": "HASHED", "path": latest.relative_to(output).as_posix(),
                               "step": step, "tree_sha256": tree_sha}
        elif status in {"PAUSED", "STOPPED"}:
            status = "HOLD"

        receipt = {
            "schema": RECEIPT_SCHEMA, "run_id": args.run_id, "status": status, "created_utc": utc_now(),
            "model": {"id": model_lock["model_id"], "revision": args.model_revision,
                      "snapshot_sha256": model_lock["snapshot_sha256"].lower(), "quantization": "4-bit NF4 QLoRA"},
            "dataset": {"id": manifest["dataset_id"], "revision": manifest["dataset_revision"],
                        "license_id": manifest["license_id"], "owner_approval_id": manifest["owner_approval_id"],
                        "rights_attestation_id": manifest["_rights_attestation_id"],
                        "rights_attestation_sha256": manifest["_rights_attestation_sha256"],
                        "train_sha256": manifest["train_sha256"].lower(), "holdout_sha256": manifest["holdout_sha256"].lower(),
                        "train_records": train_records, "holdout_records": holdout_records},
            "runtime": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "torch": torch.__version__, "transformers": transformers.__version__,
                        "peft": peft.__version__, "trl": trl.__version__,
                        "accelerate": accelerate.__version__, "cuda": torch.version.cuda,
                        "gpu": chosen["name"], "gpu_uuid": chosen["uuid"], "gpu_memory_total_mib": chosen["memory_total_mib"],
                        "gpu_memory_free_initial_mib": vram_headroom["free_mib"],
                        "gui_vram_reserve_initial_mib": vram_headroom["gui_reserve_mib"]},
            "training": {"profile": args.profile, "max_steps": total_steps,
                         "global_step": global_step, "epochs": epochs, "batch_size": batch_size,
                         "learning_rate": args.learning_rate, "train_loss": train_loss,
                         "baseline_eval_loss": baseline_eval_loss,
                         "adapter_eval_loss": adapter_eval_loss,
                         "evaluation_status": evaluation_status,
                         "gpu_temperature_initial_c": temp, "gpu_temperature_last_c": monitor["temperature"],
                         "thermal_stop_reason": monitor["thermal_reason"],
                         "gpu_resource_stop_reason": monitor["resource_reason"],
                         "gpu_memory_free_last_mib": monitor["vram_free_mib"]},
            "checkpoint": checkpoint_info, "adapter_sha256": sha256_tree(adapter_dir),
            "evidence_verified": False,
        }
        receipt_sha, receipt_path = write_training_receipt(output, receipt)
        terminal_message = f"{status}; receipt_sha256={receipt_sha}; checkpoint={checkpoint_info['status'] if checkpoint_info else 'UNAVAILABLE'}"
        if status == "PAUSED":
            events.emit("task.progress", "PAUSED", "training_paused", terminal_message, global_step, total_steps)
        elif status == "STOPPED":
            events.emit("model.stopped", "STOPPED", "training_stopped", terminal_message, global_step, total_steps)
        elif status == "HOLD":
            events.emit("task.failed", "HOLD", "training_hold", terminal_message, global_step, total_steps)
        elif status == "COMPLETED":
            events.emit("task.completed", "COMPLETED", "training_completed", terminal_message, global_step, total_steps)
        print(json.dumps({"run_id": args.run_id, "status": status, "receipt_sha256": receipt_sha}, separators=(",", ":")))
        return 0 if status in {"COMPLETED", "STOPPED", "PAUSED"} else 2
    except Exception as exc:
        status = "HOLD" if str(exc).startswith(("GPU_", "RIGHTS_", "DATASET_", "MODEL_")) else "ERROR"
        try:
            events.emit("task.failed", status, "training_failed", type(exc).__name__)
        except Exception:
            pass
        print(json.dumps({"run_id": args.run_id, "status": status, "error": type(exc).__name__}), file=sys.stderr)
        return 2
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
