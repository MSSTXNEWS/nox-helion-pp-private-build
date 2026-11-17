"""Verified owner-scoped resume admission for the EXISTING NOX V135 ZeRO-3 trainer.

No GPU import, new service, symlink traversal, output overwrite, or model-only
checkpoint acceptance. Caller must first authenticate and bind the native
resource snapshot with original verify_owner() HMAC.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from collections.abc import Mapping

_SHA = re.compile(r"^[0-9a-f]{64}$")
_STEP = re.compile(r"^checkpoint-([1-9][0-9]*)$")


def checkpoint_tree_sha256(root: Path) -> str:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("HOLD_RESUME_CHECKPOINT_DIRECTORY")
    entries = []
    for entry in sorted(root.rglob("*")):
        if entry.is_symlink():
            raise RuntimeError("HOLD_RESUME_SYMLINK")
        if entry.is_file():
            if entry.stat().st_size <= 0:
                raise RuntimeError("HOLD_RESUME_EMPTY_SHARD")
            entries.append(entry)
            if len(entries) > 2048:
                raise RuntimeError("HOLD_RESUME_TOO_MANY_FILES")
    if not entries:
        raise RuntimeError("HOLD_RESUME_EMPTY_CHECKPOINT")
    result = hashlib.sha256()
    for path in entries:
        name = path.relative_to(root).as_posix().encode("utf-8")
        result.update(len(name).to_bytes(4, "big"))
        result.update(name)
        result.update(path.stat().st_size.to_bytes(8, "big"))
        sha = hashlib.sha256()
        with path.open("rb") as src:
            for chunk in iter(lambda: src.read(4 * 1024 * 1024), b""):
                sha.update(chunk)
        result.update(sha.digest())
    return result.hexdigest()


def admit_resume(output: Path, checkpoint: Path, native: Mapping,
                 *, max_steps: int, expected_config: dict) -> dict:
    """Allow exact checkpoint-N from original output only, with full optimizer.

    The native dict is signed in the parent V135 owner admission; an arbitrary
    user-supplied local file is never sufficient authorization for recovery.
    """
    if (not isinstance(native, Mapping) or type(max_steps) is not int
            or output.is_symlink() or not output.is_dir()
            or checkpoint.is_symlink() or not checkpoint.is_dir()
            or checkpoint.parent != output or not _STEP.fullmatch(checkpoint.name)):
        raise RuntimeError("HOLD_RESUME_CHECKPOINT_SCOPE")
    step_file = checkpoint / "trainer_state.json"
    original_config = output / "deepspeed_zero3_cpu.json"
    if (step_file.is_symlink() or original_config.is_symlink()
            or not step_file.is_file() or not original_config.is_file()
            or step_file.stat().st_size > 2_000_000
            or original_config.stat().st_size > 50_000):
        raise RuntimeError("HOLD_RESUME_TRAINER_OR_CONFIG")
    try:
        state = json.loads(step_file.read_text("utf-8"))
        actual_config = json.loads(original_config.read_text("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RuntimeError("HOLD_RESUME_METADATA") from exc
    step = state.get("global_step") if isinstance(state, dict) else None
    if (type(step) is not int or step < 1 or step >= max_steps
            or checkpoint.name != f"checkpoint-{step}"):
        raise RuntimeError("HOLD_RESUME_STEP")
    if actual_config != expected_config:
        raise RuntimeError("HOLD_RESUME_DEEPSPEED_CONFIG_CHANGE")
    names = [entry.name for entry in checkpoint.rglob("*") if entry.is_file()]
    if (not any(n.endswith("optim_states.pt") for n in names)
            or not any(n.endswith("model_states.pt") for n in names)):
        raise RuntimeError("HOLD_RESUME_FULL_OPTIMIZER_MISSING")
    if (native.get("resume_checkpoint_path") != str(checkpoint)
            or native.get("resume_checkpoint_step") != step
            or native.get("resume_optimizer_scheduler_rng_verified") is not True
            or native.get("resume_offsite_restore_verified") is not True
            or native.get("resume_original_student_sha256") != native.get("student_base_sha256")):
        raise RuntimeError("HOLD_RESUME_OWNER_SIGNED_RESTORE")
    expected_sha = native.get("resume_checkpoint_tree_sha256")
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise RuntimeError("HOLD_RESUME_OWNER_SIGNED_SHA")
    actual_sha = checkpoint_tree_sha256(checkpoint)
    if not hmac.compare_digest(actual_sha, expected_sha):
        raise RuntimeError("HOLD_RESUME_TREE_SHA_MISMATCH")
    return {"state": "VERIFIED_SIGNED_FULL_OPTIMIZER_RESUME",
            "checkpoint": str(checkpoint), "start_step": step,
            "checkpoint_sha256": actual_sha, "production_promoted": False}

