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
import os
import platform
import re
import shutil
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


def sha256_tree(root: Path) -> str:
    """Hash a directory deterministically and reject symbolic links."""
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
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


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
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
    if (not isinstance(attestation, dict)
            or attestation.get("status") != "VERIFIED"
            or attestation.get("manifest_sha256", "").lower() != manifest_sha
            or attestation.get("dataset_id") != manifest["dataset_id"]
            or attestation.get("intent") != "training"):
        raise ValueError("RIGHTS_VERIFIER_ATTESTATION_MISMATCH")
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


def validate_jsonl(path: Path, label: str) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label}_INVALID_JSONL_{number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{label}_ROW_NOT_OBJECT_{number}")
            if isinstance(row.get("text"), str) and row["text"].strip():
                count += 1
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
    if count == 0:
        raise ValueError(f"{label}_EMPTY")
    return count


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


class EventWriter:
    def __init__(self, path: Path, run_id: str, task_id: str):
        self.path, self.run_id, self.task_id = path, run_id, task_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.sequence = 0

    @staticmethod
    def clean(message: str) -> str:
        message = SECRET_RE.sub(r"\1=[REDACTED]", str(message))
        message = re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", message)
        return message[:240]

    def emit(self, event_type: str, state: str, action: str, message: str,
             numerator: int | None = None, denominator: int | None = None) -> None:
        with self.lock:
            self.sequence += 1
            event = {
                "schema": EVENT_SCHEMA, "run_id": self.run_id, "event_id": uuid.uuid4().hex,
                "event_sequence": self.sequence, "event_type": event_type, "task_id": self.task_id,
                "package_id": "P04", "action_id": action, "timestamp_utc": utc_now(),
                "state": state, "source": "P04.QLoRA", "message": self.clean(message),
                "numerator": numerator, "denominator": denominator, "evidence_verified": False,
            }
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())


def validated_checkpoint(checkpoint_dir: Path, selected: Path) -> tuple[int, str]:
    if selected.is_symlink() or not selected.is_dir():
        raise ValueError("RESUME_CHECKPOINT_NOT_REGULAR_DIRECTORY")
    root = checkpoint_dir.resolve(strict=True)
    real = selected.resolve(strict=True)
    if real.parent != root or not re.fullmatch(r"checkpoint-(\d+)", real.name):
        raise ValueError("RESUME_CHECKPOINT_OUTSIDE_RUN")
    state = read_object(real / "trainer_state.json")
    step = int(real.name.split("-")[-1])
    if type(state.get("global_step")) is not int or state["global_step"] != step:
        raise ValueError("RESUME_CHECKPOINT_STEP_MISMATCH")
    model_files = ("adapter_model.safetensors", "adapter_model.bin", "model.safetensors", "pytorch_model.bin")
    if not any((real / name).is_file() and not (real / name).is_symlink() for name in model_files):
        raise ValueError("RESUME_CHECKPOINT_MODEL_MISSING")
    for name in ("optimizer.pt", "scheduler.pt"):
        if not (real / name).is_file() or (real / name).stat().st_size == 0:
            raise ValueError("RESUME_CHECKPOINT_STATE_MISSING")
    rng = list(real.glob("rng_state*.pth"))
    if not rng or any(not path.is_file() or path.is_symlink() or path.stat().st_size == 0 for path in rng):
        raise ValueError("RESUME_CHECKPOINT_RNG_MISSING")
    return step, sha256_tree(real)


def acquire_gpu_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
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
    if (max_steps != -1 and max_steps < 1) or epochs <= 0 or epochs > profile["max_epochs"]:
        parser.error("steps/epochs exceed profile")
    if batch_size < 1 or batch_size > profile["max_batch"]:
        parser.error("batch-size exceeds profile")
    if not (1e-6 <= args.learning_rate <= 1e-3 and 128 <= max_seq <= profile["max_seq"]):
        parser.error("learning-rate or max-seq-length outside profile")
    if save_steps < 1 or eval_steps < 1 or args.gpu_index < 0 or not 50 <= args.thermal_stop_c <= 90:
        parser.error("invalid save/eval/GPU/thermal setting")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.model_revision):
        parser.error("model-revision must be an immutable 40-character revision")

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
        lock_fd = acquire_gpu_lock(lock_path)
        os.write(lock_fd, (args.run_id + "\n").encode())
        os.fsync(lock_fd)

        params = {
            "run_id": args.run_id, "task_id": args.task_id,
            "model_id": model_lock["model_id"], "model_revision": args.model_revision,
            "model_snapshot_sha256": model_lock["snapshot_sha256"].lower(),
            "dataset_id": manifest["dataset_id"], "dataset_revision": manifest["dataset_revision"],
            "train_sha256": manifest["train_sha256"].lower(), "holdout_sha256": manifest["holdout_sha256"].lower(),
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
        train_dataset = load_dataset("json", data_files=str(train_path), split="train")
        eval_dataset = load_dataset("json", data_files=str(holdout_path), split="train")
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
                   "stop": False, "pause": False, "train_loss": None, "eval_loss": None}
        class Callback(TrainerCallback):
            def on_log(self, args_, state, control, logs=None, **kwargs):
                logs = logs or {}
                if "loss" in logs:
                    monitor["train_loss"] = float(logs["loss"])
                    events.emit("training.step", "RUNNING", "train_loss",
                                f"train_loss={monitor['train_loss']:.8g}",
                                int(state.global_step), int(state.max_steps))
                if "eval_loss" in logs:
                    monitor["eval_loss"] = float(logs["eval_loss"])
                    events.emit("training.step", "RUNNING", "validation_loss",
                                f"eval_loss={monitor['eval_loss']:.8g}",
                                int(state.global_step), int(state.max_steps))
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
                events.emit("checkpoint.saved", "READY", "checkpoint_saved",
                            "Transformers saved a resumable checkpoint.", int(state.global_step), int(state.max_steps))
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
        if monitor["thermal_reason"]:
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
                        "train_sha256": manifest["train_sha256"].lower(), "holdout_sha256": manifest["holdout_sha256"].lower(),
                        "train_records": train_records, "holdout_records": holdout_records},
            "runtime": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "torch": torch.__version__, "transformers": transformers.__version__,
                        "peft": peft.__version__, "trl": trl.__version__,
                        "accelerate": accelerate.__version__, "cuda": torch.version.cuda,
                        "gpu": chosen["name"], "gpu_uuid": chosen["uuid"], "gpu_memory_total_mib": chosen["memory_total_mib"]},
            "training": {"profile": args.profile, "max_steps": total_steps,
                         "global_step": global_step, "epochs": epochs, "batch_size": batch_size,
                         "learning_rate": args.learning_rate, "train_loss": float(result.training_loss),
                         "baseline_eval_loss": baseline.get("eval_loss"),
                         "adapter_eval_loss": final_eval.get("eval_loss"),
                         "gpu_temperature_initial_c": temp, "gpu_temperature_last_c": monitor["temperature"],
                         "thermal_stop_reason": monitor["thermal_reason"]},
            "checkpoint": checkpoint_info, "adapter_sha256": sha256_tree(adapter_dir),
            "evidence_verified": False,
        }
        receipt_path = output / "training-receipt.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt_sha = sha256_file(receipt_path)
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
