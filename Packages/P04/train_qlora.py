"""Fail-closed control plane for NOX P05 training runs.

This module deliberately has no training backend and performs no work on import.
A caller must supply a trusted manifest verifier and an owner-pinned backend before
any training can be started. The file implements provenance, safe paths, atomic
receipts, and the STOP/pause/resume state machine only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


MANIFEST_SCHEMA = "NOX_P05_TRAINING_MANIFEST_V1"
CHECKPOINT_SCHEMA = "NOX_P05_CHECKPOINT_RECEIPT_V1"
RESULT_SCHEMA = "NOX_P05_RESULT_RECEIPT_V1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class TrainingGateError(ValueError):
    """Raised when provenance or state preconditions are not satisfied."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_child(root: Path, relative: str) -> Path:
    """Resolve a relative path and reject traversal or symlink escape."""
    if not relative or Path(relative).is_absolute():
        raise TrainingGateError("PATH_INVALID", "A non-empty relative path is required.")
    base = root.resolve(strict=True)
    candidate = (base / relative).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise TrainingGateError("PATH_ESCAPE", "Path resolves outside the run root.") from exc
    return candidate


def atomic_write_json(path: Path, value: Any) -> str:
    """Atomically replace one JSON receipt and return the SHA-256 of its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value) + b"\n"
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Some platforms do not permit fsync on directories.
            pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return sha256_bytes(payload)


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    task_id: str
    model_id: str
    model_revision: str
    model_sha256: str
    dataset_manifest_sha256: str
    training_config_sha256: str

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, Any]) -> "RunIdentity":
        required = (
            "run_id", "task_id", "model_id", "model_revision", "model_sha256",
            "dataset_manifest_sha256", "training_config_sha256",
        )
        missing = [key for key in required if not manifest.get(key)]
        if missing:
            raise TrainingGateError("MANIFEST_INCOMPLETE", "Missing: " + ", ".join(missing))
        run_id = str(manifest["run_id"])
        if not RUN_ID_RE.fullmatch(run_id):
            raise TrainingGateError("RUN_ID_INVALID", "RunID has an invalid format.")
        for key in ("model_sha256", "dataset_manifest_sha256", "training_config_sha256"):
            if not SHA256_RE.fullmatch(str(manifest[key])):
                raise TrainingGateError("DIGEST_INVALID", key + " must be lowercase SHA-256.")
        return cls(
            run_id=run_id,
            task_id=str(manifest["task_id"]),
            model_id=str(manifest["model_id"]),
            model_revision=str(manifest["model_revision"]),
            model_sha256=str(manifest["model_sha256"]),
            dataset_manifest_sha256=str(manifest["dataset_manifest_sha256"]),
            training_config_sha256=str(manifest["training_config_sha256"]),
        )


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    verify_trusted_manifest: Optional[Callable[[Mapping[str, Any]], bool]] = None,
) -> RunIdentity:
    """Validate required identity and require an external trust/rights verifier."""
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise TrainingGateError("MANIFEST_UNSUPPORTED", "Unsupported manifest schema.")
    identity = RunIdentity.from_manifest(manifest)
    rights = manifest.get("dataset_rights")
    if not isinstance(rights, Mapping) or rights.get("status") != "approved":
        raise TrainingGateError("DATASET_RIGHTS_UNVERIFIED", "Dataset rights are not approved.")
    if not rights.get("evidence_id") or not rights.get("reviewer_id"):
        raise TrainingGateError("DATASET_EVIDENCE_MISSING", "Rights evidence is incomplete.")
    if not manifest.get("signer_key_id") or not manifest.get("signature"):
        raise TrainingGateError("SIGNATURE_MISSING", "A signed manifest is required.")
    if verify_trusted_manifest is None:
        raise TrainingGateError("TRUST_VERIFIER_UNAVAILABLE", "No trusted signature/rights verifier is configured.")
    if not verify_trusted_manifest(manifest):
        raise TrainingGateError("MANIFEST_UNTRUSTED", "Manifest signature or rights verification failed.")
    return identity


def identity_object(identity: RunIdentity) -> dict[str, str]:
    return asdict(identity)


def write_checkpoint_receipt(
    identity: RunIdentity,
    run_root: Path,
    checkpoint_relative_path: str,
) -> Path:
    checkpoint = safe_child(run_root, checkpoint_relative_path)
    if not checkpoint.is_file():
        raise TrainingGateError("CHECKPOINT_MISSING", "Checkpoint file does not exist.")
    checkpoint_sha = sha256_file(checkpoint)
    receipt_path = safe_child(run_root, "checkpoint.receipt." + checkpoint_sha + ".json")
    receipt = {
        "schema": CHECKPOINT_SCHEMA,
        "identity": identity_object(identity),
        "checkpoint_path": checkpoint.relative_to(run_root.resolve()).as_posix(),
        "checkpoint_sha256": checkpoint_sha,
        "created_utc": utc_now(),
    }
    atomic_write_json(receipt_path, receipt)
    return receipt_path


def validate_checkpoint_receipt(
    identity: RunIdentity,
    run_root: Path,
    receipt_path: Path,
) -> Path:
    root = run_root.resolve(strict=True)
    receipt_file = receipt_path.resolve(strict=True)
    try:
        receipt_file.relative_to(root)
    except ValueError as exc:
        raise TrainingGateError("RECEIPT_PATH_ESCAPE", "Receipt is outside run root.") from exc
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingGateError("CHECKPOINT_RECEIPT_INVALID", "Checkpoint receipt is unreadable.") from exc
    if receipt.get("schema") != CHECKPOINT_SCHEMA:
        raise TrainingGateError("CHECKPOINT_SCHEMA_UNSUPPORTED", "Unsupported checkpoint schema.")
    if receipt.get("identity") != identity_object(identity):
        raise TrainingGateError("CHECKPOINT_IDENTITY_MISMATCH", "Run/model/data identity differs.")
    checkpoint = safe_child(root, str(receipt.get("checkpoint_path", "")))
    if not checkpoint.is_file() or sha256_file(checkpoint) != receipt.get("checkpoint_sha256"):
        raise TrainingGateError("CHECKPOINT_DIGEST_MISMATCH", "Checkpoint bytes do not match receipt.")
    return checkpoint


class RunController:
    """Single-run state controller. STOP is terminal; PAUSED is resumable."""

    def __init__(self, identity: RunIdentity, run_root: Path):
        self.identity = identity
        self.run_root = run_root.resolve(strict=True)
        self.state_path = safe_child(self.run_root, "run-state.json")
        self.result_path = safe_child(self.run_root, "result.receipt.json")
        self._lock = threading.RLock()
        self.state = "READY"
        self.events: list[dict[str, str]] = []
        if self.state_path.exists():
            try:
                prior = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TrainingGateError("RUN_STATE_INVALID", "Persisted run state is unreadable.") from exc
            if prior.get("schema") != "NOX_P05_RUN_STATE_V1":
                raise TrainingGateError("RUN_STATE_UNSUPPORTED", "Persisted run state schema is unsupported.")
            if prior.get("identity") != identity_object(self.identity):
                raise TrainingGateError("RUN_IDENTITY_MISMATCH", "Persisted run identity differs.")
            if prior.get("state") not in ("READY", "RUNNING", "PAUSE_REQUESTED", "PAUSED", "STOPPED", "COMPLETED", "FAILED"):
                raise TrainingGateError("RUN_STATE_INVALID", "Persisted run state value is invalid.")
            if not isinstance(prior.get("events"), list):
                raise TrainingGateError("RUN_STATE_INVALID", "Persisted event history is invalid.")
            self.state = prior["state"]
            self.events = prior["events"]
        else:
            self._persist("READY", "controller-created")

    def _persist(self, state: str, reason: str) -> None:
        event = {
            "state": state,
            "reason": reason[:240],
            "at_utc": utc_now(),
            "run_id": self.identity.run_id,
            "task_id": self.identity.task_id,
        }
        next_events = [*self.events, event]
        atomic_write_json(self.state_path, {
            "schema": "NOX_P05_RUN_STATE_V1",
            "identity": identity_object(self.identity),
            "state": state,
            "events": next_events,
        })
        # Commit in-memory state only after the durable state write succeeds.
        self.events = next_events
        self.state = state

    def start(self, *, gates_verified: bool) -> None:
        with self._lock:
            if self.state != "READY":
                raise TrainingGateError("STATE_INVALID", "Only a READY run can start.")
            if not gates_verified:
                raise TrainingGateError("GATES_UNVERIFIED", "Manifest, rights and backend gates are required.")
            self._persist("RUNNING", "preflight-passed")

    def request_pause(self, reason: str = "pause-requested") -> None:
        with self._lock:
            if self.state != "RUNNING":
                raise TrainingGateError("STATE_INVALID", "Pause requires RUNNING state.")
            self._persist("PAUSE_REQUESTED", reason)

    def pause_at_checkpoint_boundary(
        self, checkpoint_relative_path: str
    ) -> Path:
        with self._lock:
            if self.state != "PAUSE_REQUESTED":
                raise TrainingGateError("STATE_INVALID", "No pause is pending.")
            receipt = write_checkpoint_receipt(
                self.identity, self.run_root, checkpoint_relative_path
            )
            self._persist("PAUSED", "checkpoint-saved-at-safe-boundary")
            return receipt

    def resume(self, checkpoint_receipt: Path) -> None:
        with self._lock:
            if self.state == "STOPPED":
                raise TrainingGateError("STOP_TERMINAL", "STOP is terminal for this RunID.")
            if self.state != "PAUSED":
                raise TrainingGateError("STATE_INVALID", "Only a PAUSED run can resume.")
            validate_checkpoint_receipt(self.identity, self.run_root, checkpoint_receipt)
            self._persist("RUNNING", "checkpoint-identity-and-digest-verified")

    def stop(self, reason: str = "stop-requested") -> Path:
        with self._lock:
            if self.state not in ("RUNNING", "PAUSE_REQUESTED", "PAUSED"):
                raise TrainingGateError("STATE_INVALID", "STOP requires an active or paused run.")
            self._persist("STOPPED", reason)
            return self.write_result("STOPPED", reason)

    def write_result(
        self,
        status: str,
        reason: str,
        *,
        backend_completed: bool = False,
    ) -> Path:
        allowed = {"SUCCEEDED", "FAILED", "STOPPED", "PAUSED"}
        if status not in allowed:
            raise TrainingGateError("RESULT_STATUS_INVALID", "Unknown terminal status.")
        if status == "SUCCEEDED" and not backend_completed:
            raise TrainingGateError("SUCCESS_WITHOUT_BACKEND", "Success requires a completed backend receipt.")
        if status == "SUCCEEDED" and self.state != "RUNNING":
            raise TrainingGateError("STATE_INVALID", "Only a running backend may complete successfully.")
        if status == "STOPPED" and self.state != "STOPPED":
            raise TrainingGateError("STATE_INVALID", "STOPPED result requires terminal STOP state.")
        if status == "PAUSED" and self.state != "PAUSED":
            raise TrainingGateError("STATE_INVALID", "PAUSED result requires checkpointed pause state.")
        if status == "FAILED" and self.state not in ("READY", "RUNNING", "PAUSE_REQUESTED"):
            raise TrainingGateError("STATE_INVALID", "FAILED result requires an unfinished run.")
        result = {
            "schema": RESULT_SCHEMA,
            "identity": identity_object(self.identity),
            "status": status,
            "reason": reason[:240],
            "created_utc": utc_now(),
            "backend_completed": backend_completed,
        }
        receipt_bytes = canonical_json_bytes(result) + b"\n"
        receipt_digest = sha256_bytes(receipt_bytes)
        archive_path = safe_child(
            self.run_root, f"result-receipts/{receipt_digest}.json"
        )
        # Preserve each status receipt; result.receipt.json remains the latest-value view.
        atomic_write_json(archive_path, result)
        atomic_write_json(self.result_path, result)
        if status == "SUCCEEDED":
            self._persist("COMPLETED", "backend-completed")
        elif status == "FAILED":
            self._persist("FAILED", reason)
        return archive_path

