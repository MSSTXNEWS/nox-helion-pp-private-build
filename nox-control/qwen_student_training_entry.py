#!/usr/bin/env python3
"""Qwen9B candidate entry for NOX's existing single Supervisor trainer slot.

Not installed or queued by this file. An owner-native admission must explicitly
pin this entry, its contract, dataset, runtime and base. It never clears STOP,
starts another service, merges adapters or changes chat. Explicit admission
may stage pinned public base files in sealed memory inside this process.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import fcntl
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import signal
import sys
import tempfile
import threading
import time

from owner_qwen_training_contract import (
    GIB, Hold, MANIFEST_SHA, MODEL_ID, PROOF_SCHEMA, REQUIRED_PACKAGE_VERSIONS,
    REVISION, SCHEMA, canonical_sha, sha256_file, text_projection_names,
    validate_environment, validate_resume_lineage, validate_target_inventory,
    validate_update_evidence, verify_base_files,
    validate_manifest, verify_proof,
)
from owner_qwen_memfd import SealedModel, tiny_safetensors_smoke

ROOT = Path("/root/nox")
SERVICE = "nox-train-volta-t866u"
ADMISSION = ROOT / "state/owner_training_admission.json"
POLICY = ROOT / "state/task_boost_mode.json"
LEASE = ROOT / "state/forge_training.lock"
MANUAL_STOPS = tuple(ROOT / p for p in (
    "STOP", "STOP.flag", "stop.flag", ".stop", "state/STOP", "program/STOP")) + (Path("/workspace/NOX_STOP"),)
YIELD_FLAGS = (ROOT / "state/TRAIN_HOLD.flag", ROOT / "state/TRAIN_PAUSE_REQUEST.flag")
TERMINATE_REQUESTED = False
PROCESS_LEASES = []
CHECKPOINT_NAME = re.compile(r"checkpoint-u\d{8}-a\d{8}-g\d{20}")


def read_json(path, maximum=2 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise Hold("HOLD_BOUNDED_JSON_PATH")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Hold("HOLD_JSON_OBJECT_REQUIRED")
    return value


def atomic_json(path, value, *, replace=True):
    path = Path(path)
    if path.is_symlink():
        raise Hold("HOLD_OUTPUT_SYMLINK")
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()
    fd, tmp = tempfile.mkstemp(prefix=".qwen-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def signal_stop(*_):
    global TERMINATE_REQUESTED
    TERMINATE_REQUESTED = True


def stop_reason():
    if any(p.exists() or p.is_symlink() for p in MANUAL_STOPS):
        return "MANUAL_OWNER_STOP"
    if TERMINATE_REQUESTED:
        return "CONTROLLED_PROCESS_YIELD"
    if any(p.exists() or p.is_symlink() for p in YIELD_FLAGS):
        return "EXISTING_TRAINER_HOLD_OR_PAUSE"
    return None


def check_path(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path
            or any(p.is_symlink() for p in (*path.parents, path))):
        raise Hold("HOLD_NATIVE_PATH_OR_SYMLINK")
    return path


def admission(args):
    if stop_reason():
        raise Hold("HOLD_TRAINING_STOP_REQUESTED")
    if sha256_file(ADMISSION) != args.admission_sha256:
        raise Hold("HOLD_QWEN_ADMISSION_CHANGED")
    value = read_json(ADMISSION)
    student = value.get("student_profile", {})
    expected = {
        "schema": "NOX_QWEN35_9B_SINGLE_TRAINER_V1",
        "model_id": MODEL_ID, "revision": REVISION,
        "base_manifest_sha256": MANIFEST_SHA,
        "base_directory": str(args.base_directory),
        "output_directory": str(args.output_directory),
        "train_sha256": args.train_sha256, "holdout_sha256": args.holdout_sha256,
        "base_transport": args.base_transport,
        "dataset_manifest_sha256": args.dataset_manifest_sha256,
        "physical_gpu": 1, "training_service": SERVICE,
    }
    if (value.get("schema") != "NOX_OWNER_TRAINING_ADMISSION_V1"
            or value.get("request") != args.request
            or any(student.get(k) != v for k, v in expected.items())
            or student.get("successful_updates_goal") != args.successful_updates
            or not isinstance(student.get("runtime_versions"), dict)):
        raise Hold("HOLD_QWEN_EXPLICIT_NATIVE_ADMISSION_REQUIRED")
    for name in ("qwen_student_training_entry.py", "owner_qwen_training_contract.py", "owner_qwen_memfd.py"):
        path = Path(__file__).with_name(name)
        if (str(path) != str(ROOT / "scripts" / name)
                or value.get("sources", {}).get(str(path)) != sha256_file(path)):
            raise Hold("HOLD_QWEN_INSTALLED_SOURCE_PIN")
    policy = read_json(POLICY, 16000)
    if (policy.get("enabled") is not True or policy.get("mode") != "TASK_BOOST"
            or policy.get("training_allowed") is not True or policy.get("training_service") != SERVICE
            or policy.get("training_gpu") != 1):
        raise Hold("HOLD_EXISTING_TRAINER_POLICY")
    return student


@contextmanager
def single_trainer_lease():
    fd = os.open(LEASE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold("HOLD_EXISTING_TRAINER_WRITER_ACTIVE") from exc
        PROCESS_LEASES.append(fd)
        yield
    except BaseException:
        if fd not in PROCESS_LEASES:
            os.close(fd)
        raise
    # The fd intentionally remains open until process exit. Releasing before
    # CUDA context teardown would let another trainer acquire the same GPU.


def process_identity():
    raw = Path("/proc/self/stat").read_text()
    fields = raw[raw.rindex(")") + 2:].split()
    return {"pid": os.getpid(), "start_ticks": int(fields[19]),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def check_resources(output, extra_disk=0, memory_headroom=0):
    maximum = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    current = Path("/sys/fs/cgroup/memory.current").read_text().strip()
    if not maximum.isdigit() or not current.isdigit():
        raise Hold("HOLD_CGROUP_MEMORY_TELEMETRY")
    if int(maximum) - int(current) < 24 * GIB + memory_headroom:
        raise Hold("HOLD_QWEN_CGROUP_RESERVE")
    if shutil.disk_usage(output).free < 8 * GIB + extra_disk:
        raise Hold("HOLD_QWEN_CHECKPOINT_DISK_RESERVE")


def read_messages(path, expected, minimum):
    if sha256_file(path) != expected or Path(path).stat().st_size > 32 * 1024 * 1024:
        raise Hold("HOLD_STUDENT_DATASET_SHA_OR_SIZE")
    rows, seen = [], set()
    with Path(path).open(encoding="utf8", newline="\n") as stream:
        for line in stream:
            value = json.loads(line)
            messages = value.get("messages") if isinstance(value, dict) else None
            if (not isinstance(messages, list) or not messages
                    or any(not isinstance(m, dict) or set(m) != {"role", "content"}
                           or m["role"] not in {"system", "user", "assistant"}
                           or not isinstance(m["content"], str) for m in messages)
                    or not any(m["role"] == "assistant" for m in messages)):
                raise Hold("HOLD_STUDENT_MESSAGES_SCHEMA")
            key = canonical_sha(messages)
            if key in seen:
                continue
            seen.add(key); rows.append(messages)
    if len(rows) < minimum:
        raise Hold("HOLD_STUDENT_DATASET_TOO_SMALL")
    return rows, seen


def trainable_inventory(model, torch):
    records = []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if ("lora_" not in name or "model.language_model.layers." not in name
                or "visual" in name or ".mtp." in name or not parameter.is_cuda):
            raise Hold("HOLD_UNEXPECTED_STUDENT_TRAINABLE_PARAMETER")
        if parameter.dtype != torch.float32:
            parameter.data = parameter.data.float()
        records.append((name, list(parameter.shape), parameter.numel()))
    if len(records) != 2 * len(text_projection_names()):
        raise Hold("HOLD_STUDENT_ADAPTER_TENSOR_COUNT")
    return {"tensors": len(records), "parameters": sum(r[2] for r in records),
            "schema_sha256": canonical_sha(records), "dtype": "float32"}


def adapter_hash(model, torch):
    import hashlib
    h = hashlib.sha256()
    for name, parameter in sorted(model.named_parameters()):
        if not parameter.requires_grad:
            continue
        if parameter.dtype != torch.float32:
            raise Hold("HOLD_ADAPTER_PRECISION_DRIFT")
        value = parameter.detach().cpu().contiguous()
        if not bool(torch.isfinite(value).all()):
            raise Hold("HOLD_NONFINITE_ADAPTER")
        h.update(name.encode()); h.update(canonical_sha(list(value.shape)).encode())
        h.update(value.numpy().tobytes())
    return h.hexdigest()


def optimizer_step_number(optimizer):
    steps = []
    for group in optimizer.param_groups:
        for p in group["params"]:
            value = optimizer.state.get(p, {}).get("step", 0)
            steps.append(int(value.item()) if hasattr(value, "item") else int(value))
    if not steps or len(set(steps)) != 1:
        raise Hold("HOLD_PARTIAL_OPTIMIZER_STEP_STATE")
    return steps[0]


def encoded_example(tokenizer, messages):
    if messages[-1]["role"] != "assistant":
        raise Hold("HOLD_FINAL_ASSISTANT_TARGET_REQUIRED")
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    if not text.startswith(prefix):
        raise Hold("HOLD_QWEN_ASSISTANT_PREFIX_MISMATCH")
    batch = tokenizer(text, truncation=True, max_length=512,
                      padding=False, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(batch["input_ids"])
    offsets = batch.pop("offset_mapping")
    if len(ids) < 2 or len(offsets) != len(ids):
        raise Hold("HOLD_EMPTY_STUDENT_TRAINING_SEQUENCE")
    labels = [token if start >= len(prefix) else -100 for token, (start, _) in zip(ids, offsets)]
    if sum(v != -100 for v in labels) < 2:
        raise Hold("HOLD_NO_ASSISTANT_TOKENS_AFTER_TRUNCATION")
    return {"input_ids": ids, "attention_mask": list(batch.get("attention_mask", [1] * len(ids))),
            "labels": labels, "example_sha256": canonical_sha(messages)}


def holdout_evaluation_due(successful_total, goal_total, elapsed_since_save):
    """Keep a measured holdout at most five successful updates behind the trainer.

    The existing guard latches EVALUATION_STALE at a larger update gap. The
    previous 300-second-only cadence was reset by five-step checkpoint saves,
    making a fast 1000-step window hit that latch without another evaluation.
    This is a trainer scheduling fix, not a relaxation of guard thresholds.
    """
    if (type(successful_total) is not int or type(goal_total) is not int
            or not 0 <= successful_total <= goal_total <= 1000
            or type(elapsed_since_save) not in (int, float)
            or not math.isfinite(elapsed_since_save) or elapsed_since_save < 0):
        raise Hold("HOLD_HOLDOUT_EVALUATION_SCHEDULE_INPUT")
    return (successful_total == goal_total
            or (successful_total > 0 and successful_total % 5 == 0)
            or elapsed_since_save >= 300)


def admit_tokenized_dataset(tokenizer, train, holdout):
    result = []; records = []
    for name, rows, minimum in (("train", train, 40), ("holdout", holdout, 8)):
        accepted = []; rejected = {}
        for row in rows:
            try:
                accepted.append(encoded_example(tokenizer, row))
            except Hold as exc:
                if str(exc) not in {"HOLD_NO_ASSISTANT_TOKENS_AFTER_TRUNCATION", "HOLD_EMPTY_STUDENT_TRAINING_SEQUENCE"}:
                    raise
                rejected[str(exc)] = rejected.get(str(exc), 0) + 1
        if len(accepted) < minimum:
            raise Hold("HOLD_TOKENIZED_" + name.upper() + "_ACCEPTED_COUNT")
        record = {"split": name, "input_rows": len(rows), "accepted_rows": len(accepted),
                  "rejected_reasons": rejected,
                  "accepted_example_ids_sha256": canonical_sha([r["example_sha256"] for r in accepted]),
                  "tokenized_labels_sha256": canonical_sha(accepted),
                  "assistant_target_tokens": sum(sum(v != -100 for v in r["labels"]) for r in accepted)}
        result.append(accepted); records.append(record)
    return result[0], result[1], {"schema": "NOX_QWEN_TOKENIZED_CORPUS_V1", "sequence_length": 512,
                                 "assistant_only_loss": True, "splits": records, "content_exported": False}


def frozen_batch(tokenizer, encoded, torch):
    return {key: torch.tensor([encoded[key]], dtype=torch.long, device="cuda:0")
            for key in ("input_ids", "attention_mask", "labels")}


def evaluate(model, tokenizer, rows, torch):
    model.eval()
    values = []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        for row in rows:
            loss = model(**frozen_batch(tokenizer, row, torch)).loss.float()
            if not bool(torch.isfinite(loss)):
                raise Hold("HOLD_NONFINITE_HOLDOUT")
            values.append(float(loss))
    model.train()
    return sum(values) / len(values)


def runtime_observation(torch):
    return {"python_version": list(sys.version_info[:3]), "torch_version": torch.__version__,
            "torch_cuda": torch.version.cuda, "torch_arch_list": torch.cuda.get_arch_list(),
            "device_capability": list(torch.cuda.get_device_capability(0)),
            "packages": {name: importlib.metadata.version(name) for name in REQUIRED_PACKAGE_VERSIONS},
            "optional_fast_kernels_present": [name for name in ("flash_attn", "fla", "causal_conv1d", "liger_kernel")
                                              if importlib.util.find_spec(name) is not None]}


def kernel_smoke(torch, bnb):
    x = torch.randn(16, 16, device="cuda", dtype=torch.float16, requires_grad=True)
    w = torch.randn(16, 16, device="cuda", dtype=torch.float16, requires_grad=True)
    ((x @ w).float().square().mean()).backward()
    if not bool(torch.isfinite(x.grad).all() and torch.isfinite(w.grad).all()):
        raise Hold("HOLD_FP16_KERNEL_BACKWARD")
    layer = bnb.nn.Linear4bit(64, 64, bias=False, compute_dtype=torch.float16,
                             compress_statistics=True, quant_type="nf4").to("cuda")
    for p in layer.parameters():
        p.requires_grad_(False)
    sample = torch.randn(4, 64, device="cuda", dtype=torch.float16, requires_grad=True)
    layer(sample).float().square().mean().backward()
    if sample.grad is None or not bool(torch.isfinite(sample.grad).all()):
        raise Hold("HOLD_NF4_KERNEL_BACKWARD")
    del x, w, sample, layer
    torch.cuda.empty_cache()
    return {"fp16_matmul_backward": True, "nf4_input_backward": True}


def _tuples(value):
    return tuple(_tuples(x) for x in value) if isinstance(value, list) else value


def save_checkpoint(output, model, optimizer, scheduler, scaler, state, lineage, torch):
    check_resources(output, extra_disk=2 * GIB)
    name = (f"checkpoint-u{state['successful_total']:08d}-a{state['attempted_total']:08d}"
            f"-g{time.time_ns():020d}")
    target = output / name
    if target.exists():
        raise Hold("HOLD_STUDENT_CHECKPOINT_COLLISION")
    # Fail before writing a new checkpoint if its ownership ledger is invalid.
    # This cannot repair an old failed publication, but preserves the last
    # acknowledged pointer and every existing optimizer/RNG snapshot.
    ledger_path = output / "owner_checkpoints.json"
    ledger = read_json(ledger_path) if ledger_path.exists() else {
        "schema": "NOX_QWEN_OWNED_CHECKPOINTS_V1",
        "lineage_sha256": canonical_sha(lineage), "checkpoints": []}
    if (ledger.get("schema") != "NOX_QWEN_OWNED_CHECKPOINTS_V1"
            or ledger.get("lineage_sha256") != canonical_sha(lineage)
            or not isinstance(ledger.get("checkpoints"), list)):
        raise Hold("HOLD_CHECKPOINT_OWNERSHIP_LEDGER")
    temporary = Path(tempfile.mkdtemp(prefix=".checkpoint-", dir=output))
    model.save_pretrained(temporary, safe_serialization=True, save_embedding_layers=False)
    torch.save(optimizer.state_dict(), temporary / "optimizer.pt")
    torch.save(scheduler.state_dict(), temporary / "scheduler.pt")
    torch.save(scaler.state_dict(), temporary / "scaler.pt")
    torch.save({"cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}, temporary / "rng_state.pt")
    atomic_json(temporary / "python_rng.json", {"state": random.getstate()})
    atomic_json(temporary / "student_state.json", state)
    atomic_json(temporary / "lineage.json", lineage)
    paths = list(temporary.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in paths) or sum(p.stat().st_size for p in paths) > 2 * GIB:
        raise Hold("HOLD_STUDENT_CHECKPOINT_SIZE_OR_SCOPE")
    record = {"schema": "NOX_QWEN35_9B_CHECKPOINT_V1", "directory": name,
              "successful_total": state["successful_total"], "attempted_total": state["attempted_total"],
              "lineage_sha256": canonical_sha(lineage), "adapter_tensor_sha256": adapter_hash(model, torch),
              "holdout_evaluated_successful_total": state["holdout_evaluated_successful_total"],
              "holdout_loss": state["last_holdout_loss"],
              "files_sha256": {p.name: sha256_file(p) for p in paths},
              "process_identity": process_identity()}
    atomic_json(temporary / "checkpoint_manifest.json", record)
    for path in temporary.iterdir():
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    os.rename(temporary, target)
    fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    ledger["checkpoints"].append({"directory": name,
        "manifest_sha256": sha256_file(target / "checkpoint_manifest.json"),
        "successful_total": state["successful_total"], "attempted_total": state["attempted_total"],
        "evaluated_at_current_step": state["holdout_evaluated_successful_total"] == state["successful_total"],
        "holdout_loss": state["last_holdout_loss"], "retained": True})
    atomic_json(ledger_path, ledger)
    # Commit the owner ledger before publishing the new latest pointer.
    # A failed ledger write leaves the old pointer intact. Do not delete
    # the new checkpoint folder: it may contain the only fresh optimizer.
    atomic_json(output / "latest_checkpoint.json", {"directory": name,
                "manifest_sha256": sha256_file(target / "checkpoint_manifest.json")})
    prune_checkpoints(output, lineage)
    return target, record


def prune_checkpoints(output, lineage):
    """Plan only: an online trainer cannot certify independent offsite restore.

    Preserve latest, previous, best evaluated and accepted checkpoint; do not
    delete even older locally hashed optimizer/RNG snapshots here. The existing
    native owner cleanup writer handles proof-gated deletion separately.
    """
    output = check_path(output)
    if (not output.is_relative_to(ROOT / "lora/qwen35_9b")
            or output == ROOT / "lora/qwen35_9b"):
        raise Hold("HOLD_CHECKPOINT_RETENTION_OUTPUT_SCOPE")
    ledger_path = output / "owner_checkpoints.json"
    ledger = read_json(ledger_path)
    if (ledger.get("schema") != "NOX_QWEN_OWNED_CHECKPOINTS_V1"
            or ledger.get("lineage_sha256") != canonical_sha(lineage)):
        raise Hold("HOLD_CHECKPOINT_RETENTION_LINEAGE")
    entries = ledger.get("checkpoints", [])
    if not isinstance(entries, list) or len(entries) > 2000:
        raise Hold("HOLD_CHECKPOINT_RETENTION_LEDGER_BOUND")
    active = [r for r in entries if r.get("retained") is True]
    if len({r["directory"] for r in active}) != len(active):
        raise Hold("HOLD_CHECKPOINT_RETENTION_DUPLICATE")
    for row in active:
        if not CHECKPOINT_NAME.fullmatch(row.get("directory", "")):
            raise Hold("HOLD_CHECKPOINT_RETENTION_NAME")
    latest = read_json(output / "latest_checkpoint.json")
    if not any(r["directory"] == latest["directory"] and r["manifest_sha256"] == latest["manifest_sha256"] for r in active):
        raise Hold("HOLD_CHECKPOINT_RETENTION_LATEST")
    ordered = sorted(active, key=lambda r: (r["successful_total"], r["attempted_total"], r["directory"]))
    keep = {r["directory"] for r in ordered[-2:]} | {latest["directory"]}
    measured = [r for r in active if r.get("evaluated_at_current_step") is True
                and type(r.get("holdout_loss")) in (int, float) and math.isfinite(r["holdout_loss"])]
    if measured:
        keep.add(min(measured, key=lambda r: r["holdout_loss"])["directory"])
    certificate_path = output / "owner_acceptance.json"
    if certificate_path.exists():
        certificate = read_json(certificate_path)
        verify_proof(certificate, lineage=lineage, minimum_updates=6)
        accepted_path = Path(certificate["checkpoint"])
        if accepted_path.parent != output or not CHECKPOINT_NAME.fullmatch(accepted_path.name):
            raise Hold("HOLD_CHECKPOINT_RETENTION_ACCEPTANCE_SCOPE")
        keep.add(accepted_path.name)
    # The trainer can verify local files but cannot attest an independent
    # offsite restore or a cleanup writer lease. An owner acceptance receipt
    # alone is not recovery proof. Never unlink unique optimizer/RNG history
    # from the online trainer merely to reclaim disk.
    # Only the EXISTING owner cleanup handler may remove exact allowlisted
    # files after its own verified backup/restore and single-writer checks.
    pending = sorted(r["directory"] for r in active if r["directory"] not in keep)
    return {
        "retained": sorted(r["directory"] for r in active),
        "deleted_verified_own_checkpoints": 0,
        "pending_external_cleanup": pending,
        "cleanup_hold": ("HOLD_INDEPENDENT_RESTORE_AND_SINGLE_CLEANUP_WRITER"
                         if pending else None),
    }


def load_checkpoint(output, model, optimizer, scheduler, scaler, lineage, torch):
    from peft import set_peft_model_state_dict, get_peft_model_state_dict
    from safetensors.torch import load_file
    pointer = read_json(output / "latest_checkpoint.json")
    name = pointer.get("directory", "")
    if not CHECKPOINT_NAME.fullmatch(name):
        raise Hold("HOLD_STUDENT_CHECKPOINT_POINTER")
    path = check_path(output / name)
    if sha256_file(path / "checkpoint_manifest.json") != pointer.get("manifest_sha256"):
        raise Hold("HOLD_STUDENT_CHECKPOINT_MANIFEST_SHA")
    record = read_json(path / "checkpoint_manifest.json")
    required = {"adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "scheduler.pt",
                "scaler.pt", "rng_state.pt", "python_rng.json", "student_state.json", "lineage.json"}
    files = record.get("files_sha256", {})
    if not required <= set(files) or any(Path(n).name != n for n in files):
        raise Hold("HOLD_INCOMPLETE_STUDENT_CHECKPOINT")
    for name, sha in files.items():
        if sha256_file(path / name) != sha:
            raise Hold("HOLD_STUDENT_CHECKPOINT_FILE_SHA")
    validate_resume_lineage(read_json(path / "lineage.json"), lineage)
    adapter = load_file(str(path / "adapter_model.safetensors"), device="cpu")
    expected_keys = get_peft_model_state_dict(model, save_embedding_layers=False)
    if (set(adapter) != set(expected_keys)
            or any(adapter[n].shape != expected_keys[n].shape or not bool(torch.isfinite(adapter[n]).all()) for n in adapter)):
        raise Hold("HOLD_STUDENT_ADAPTER_RELOAD_SCHEMA")
    set_peft_model_state_dict(model, adapter, adapter_name="default")
    optimizer.load_state_dict(torch.load(path / "optimizer.pt", map_location="cpu", weights_only=True))
    scheduler.load_state_dict(torch.load(path / "scheduler.pt", map_location="cpu", weights_only=True))
    scaler.load_state_dict(torch.load(path / "scaler.pt", map_location="cpu", weights_only=True))
    rng = torch.load(path / "rng_state.pt", map_location="cpu", weights_only=True)
    torch.set_rng_state(rng["cpu"]); torch.cuda.set_rng_state_all(rng["cuda"])
    random.setstate(_tuples(read_json(path / "python_rng.json")["state"]))
    state = read_json(path / "student_state.json")
    if (state.get("successful_total") != record["successful_total"]
            or optimizer_step_number(optimizer) != state["successful_total"]
            or adapter_hash(model, torch) != record["adapter_tensor_sha256"]):
        raise Hold("HOLD_STUDENT_RESTORE_COUNTER_OR_TENSOR")
    return state, path, record


def run(args):
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "1" or os.environ.get("BNB_CUDA_VERSION"):
        raise Hold("HOLD_SINGLE_GPU1_OR_BNB_OVERRIDE")
    for path in (args.base_directory, args.output_directory, args.manifest, args.train_jsonl,
                 args.holdout_jsonl, args.dataset_manifest):
        check_path(path)
    if (not args.output_directory.is_relative_to(ROOT / "lora/qwen35_9b")
            or args.output_directory == ROOT / "lora/qwen35_9b"):
        raise Hold("HOLD_NEW_STUDENT_OUTPUT_NAMESPACE")
    if not 5 <= args.successful_updates <= 1000 or (not args.resume and args.successful_updates != 5):
        raise Hold("HOLD_STUDENT_UPDATE_WINDOW")
    signal.signal(signal.SIGTERM, signal_stop); signal.signal(signal.SIGINT, signal_stop)
    with single_trainer_lease(), ExitStack() as resources:
        profile = admission(args)
        args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        output = args.output_directory
        if not args.resume and any(output.iterdir()):
            raise Hold("HOLD_EXISTING_STUDENT_RUN_USE_RESUME")
        check_resources(output, extra_disk=2 * GIB, memory_headroom=8 * GIB)
        if sha256_file(args.dataset_manifest) != args.dataset_manifest_sha256:
            raise Hold("HOLD_DATASET_PROVENANCE_MANIFEST_SHA")
        data_proof = read_json(args.dataset_manifest)
        if (data_proof.get("schema") != "NOX_QWEN35_CORPUS_SNAPSHOT_V1"
                or data_proof.get("source_loader_sha256") != "703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a"
                or data_proof.get("train_sha256") != args.train_sha256
                or data_proof.get("holdout_sha256") != args.holdout_sha256
                or not data_proof.get("sources") or data_proof.get("content_exported") is not False):
            raise Hold("HOLD_DATASET_NATIVE_PROVENANCE_REQUIRED")
        train, train_ids = read_messages(args.train_jsonl, args.train_sha256, 40)
        holdout, holdout_ids = read_messages(args.holdout_jsonl, args.holdout_sha256, 8)
        if train_ids & holdout_ids:
            raise Hold("HOLD_TRAIN_HOLDOUT_LEAKAGE")
        os.environ.update(USE_HUB_KERNELS="NO", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                          TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4")
        import torch
        import bitsandbytes as bnb
        from transformers import AutoTokenizer, BitsAndBytesConfig, Qwen3_5ForConditionalGeneration
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise Hold("HOLD_ONE_LEASED_CUDA_DEVICE_REQUIRED")
        observed = runtime_observation(torch)
        validate_environment(observed)
        versions = {"python": observed["python_version"], "torch": observed["torch_version"],
                    "cuda": observed["torch_cuda"], "packages": observed["packages"]}
        if versions != profile["runtime_versions"]:
            raise Hold("HOLD_NATIVE_RUNTIME_SNAPSHOT_DRIFT")
        torch.set_num_threads(4)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.cuda.set_per_process_memory_fraction(0.85, 0)
        random.seed(42); torch.manual_seed(42); torch.cuda.manual_seed_all(42)
        smoke = kernel_smoke(torch, bnb)
        admission(args)
        base_directory = args.base_directory
        staging = {"state": "PREEXISTING_VERIFIED_REGULAR_BASE_FILES"}
        registry = None
        if args.base_transport == "sealed-memfd":
            if args.base_directory != ROOT / "state/qwen_memfd":
                raise Hold("HOLD_MEMFD_PARENT_SCOPE")
            if sha256_file(args.manifest) != MANIFEST_SHA:
                raise Hold("HOLD_QWEN_MANIFEST_SHA")
            files = validate_manifest(read_json(args.manifest))
            guard_lock = threading.Lock()
            checked = [0.0]

            def stage_guard(additional):
                if stop_reason():
                    raise Hold("HOLD_TRAINING_STOP_REQUESTED")
                with guard_lock:
                    now = time.monotonic()
                    if additional > 1024 * 1024 or now - checked[0] >= 1:
                        admission(args)
                        check_resources(output, extra_disk=2 * GIB,
                                        memory_headroom=24 * GIB + additional)
                        checked[0] = now

            registry = resources.enter_context(SealedModel(
                args.base_directory, guard=stage_guard, streams=4,
                progress=lambda item: print(json.dumps({"state": "PINNED_PUBLIC_BASE_STAGING", **item}), flush=True)))
            smoke["memfd"] = tiny_safetensors_smoke(registry.directory)
            staging = registry.stage(files)
            base_directory = registry.directory
        base = verify_base_files(base_directory, args.manifest,
                                 on_file=lambda _: admission(args), sealed_registry=registry)
        admission(args); check_resources(output, extra_disk=2 * GIB, memory_headroom=16 * GIB)
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
        tokenizer = AutoTokenizer.from_pretrained(str(base_directory), local_files_only=True,
                                                  trust_remote_code=False)
        train, holdout, tokenized_proof = admit_tokenized_dataset(tokenizer, train, holdout)
        print(json.dumps({"state": "REAL_CORPUS_TOKENIZED_ADMISSION", **tokenized_proof}), flush=True)
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            str(base_directory), local_files_only=True, trust_remote_code=False,
            quantization_config=quant, device_map={"": 0}, dtype=torch.float16,
            attn_implementation="eager", use_kernels=False)
        targets = validate_target_inventory(dict(model.named_modules()))
        model.config.use_cache = False
        if hasattr(model.config, "text_config"):
            model.config.text_config.use_cache = False
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                                gradient_checkpointing_kwargs={"use_reentrant": False})
        config = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                            task_type="CAUSAL_LM", target_modules=targets)
        model = get_peft_model(model, config)
        model.peft_config["default"].base_model_name_or_path = MODEL_ID
        model.peft_config["default"].revision = REVISION
        inventory = trainable_inventory(model, torch)
        parameters = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(parameters, lr=5e-5, weight_decay=0.01, fused=False, foreach=False)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda n: max(0.1, 1.0 - n / 50_000))
        scaler = torch.amp.GradScaler("cuda", init_scale=1.0, growth_interval=2000)
        lineage = {"schema": SCHEMA, "base": base, "targets": inventory, "target_names": targets,
                   "train_sha256": args.train_sha256, "holdout_sha256": args.holdout_sha256,
                   "dataset_manifest_sha256": args.dataset_manifest_sha256,
                   "tokenized_corpus": tokenized_proof,
                   "runtime_versions": versions, "precision": "NF4_FP16_FP32_LORA",
                   "optimizer": "AdamW_UNFUSED_FP32", "learning_rate": 5e-5, "weight_decay": 0.01,
                   "sequence_length": 512, "accumulation": 8, "seed": 42, "planned_updates": 50_000,
                   "loss_scope": "LAST_ASSISTANT_TOKENS_ONLY",
                   "entry_sha256": sha256_file(__file__),
                   "contract_sha256": sha256_file(Path(__file__).with_name("owner_qwen_training_contract.py")),
                   "memfd_source_sha256": sha256_file(Path(__file__).with_name("owner_qwen_memfd.py"))}
        checkpoint = None
        restart_verified = False
        if args.resume:
            state, checkpoint, previous_record = load_checkpoint(output, model, optimizer, scheduler, scaler, lineage, torch)
            previous_identity = previous_record.get("process_identity", {})
            restart_verified = (set(previous_identity) == {"pid", "start_ticks", "boot_id"}
                                and previous_identity != process_identity())
            if not restart_verified:
                raise Hold("HOLD_NEW_PROCESS_CHECKPOINT_RELOAD_NOT_PROVEN")
            restored_holdout = evaluate(model, tokenizer, holdout, torch)
            if (state.get("holdout_evaluated_successful_total") == state["successful_total"]
                    and abs(restored_holdout - state["last_holdout_loss"]) > max(0.01, abs(state["last_holdout_loss"]) * 0.01)):
                raise Hold("HOLD_STUDENT_RELOAD_HOLDOUT_MISMATCH")
            state["last_holdout_loss"] = restored_holdout
            state["holdout_evaluated_successful_total"] = state["successful_total"]
            if restored_holdout > state["initial_holdout_loss"] * 1.05 + 0.01:
                raise Hold("HOLD_STUDENT_RELOADED_HOLDOUT_REGRESSION")
            if args.successful_updates > 6:
                certificate = read_json(output / "owner_acceptance.json")
                verify_proof(certificate, lineage=lineage, minimum_updates=6)
                certified = certificate["update_evidence"]
                if state["update_evidence"][:len(certified)] != certified:
                    raise Hold("HOLD_CONTINUOUS_RESUME_ACCEPTED_PREFIX_MISMATCH")
        else:
            initial = evaluate(model, tokenizer, holdout, torch)
            state = {"successful_total": 0, "attempted_total": 0, "skipped_total": 0, "data_cursor": 0,
                     "initial_holdout_loss": initial, "last_holdout_loss": initial,
                     "holdout_evaluated_successful_total": 0, "update_evidence": []}
            atomic_json(output / "owner_lineage.json", lineage)
        start_success = state["successful_total"]
        if start_success >= args.successful_updates:
            raise Hold("HOLD_STUDENT_GOAL_ALREADY_COMPLETE")
        before_hash = adapter_hash(model, torch)
        last_save = time.monotonic()
        reason = None
        consecutive_skips = 0
        while state["successful_total"] < args.successful_updates:
            try:
                admission(args); check_resources(output, extra_disk=2 * GIB)
            except Hold as exc:
                reason = str(exc); break
            model.train(); optimizer.zero_grad(set_to_none=True)
            losses = []
            cursor_before = state["data_cursor"]
            batch_ids = []
            for _ in range(8):
                if stop_reason():
                    reason = stop_reason(); break
                messages = train[state["data_cursor"] % len(train)]
                state["data_cursor"] += 1
                batch_ids.append(messages["example_sha256"])
                with torch.autocast("cuda", dtype=torch.float16):
                    loss = model(**frozen_batch(tokenizer, messages, torch)).loss.float()
                if not bool(torch.isfinite(loss)):
                    raise Hold("HOLD_NONFINITE_STUDENT_MICROBATCH")
                losses.append(float(loss.detach()))
                scaler.scale(loss / 8).backward()
            if reason:
                optimizer.zero_grad(set_to_none=True)
                state["data_cursor"] = cursor_before
                break
            scaler.unscale_(optimizer)
            if any(p.grad is None for p in parameters):
                raise Hold("HOLD_MISSING_ADAPTER_GRADIENT")
            finite = all(bool(torch.isfinite(p.grad).all()) for p in parameters)
            step_before = optimizer_step_number(optimizer)
            if finite:
                torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
            scale_before = scaler.get_scale()
            scaler.step(optimizer); scaler.update()
            state["attempted_total"] += 1
            skipped = not finite or scaler.get_scale() < scale_before
            if skipped:
                state["skipped_total"] += 1; consecutive_skips += 1
                state["data_cursor"] = cursor_before
                if optimizer_step_number(optimizer) != step_before:
                    raise Hold("HOLD_SKIP_CHANGED_OPTIMIZER_STATE")
                if consecutive_skips >= 8:
                    reason = "HOLD_REPEATED_AMP_SKIPS"; break
                continue
            after_hash = adapter_hash(model, torch)
            proof = {"optimizer_step_before": step_before, "optimizer_step_after": optimizer_step_number(optimizer),
                     "adapter_sha_before": before_hash, "adapter_sha_after": after_hash,
                     "amp_skipped": False, "finite_gradients": True, "loss": sum(losses) / len(losses),
                     "training_example_sha256": batch_ids}
            validate_update_evidence(proof)
            scheduler.step()
            state["successful_total"] += 1; state["update_evidence"].append(proof)
            before_hash = after_hash; consecutive_skips = 0
            reason = stop_reason()
            evaluation_due = holdout_evaluation_due(
                state["successful_total"], args.successful_updates, time.monotonic() - last_save)
            checkpoint_due = evaluation_due or state["successful_total"] <= 6 or state["successful_total"] % 5 == 0
            if reason or checkpoint_due:
                # Chat/STOP preemption checkpoints promptly; it does not run an
                # eight-example evaluation before releasing the process.
                if not reason and evaluation_due:
                    measured = evaluate(model, tokenizer, holdout, torch)
                    state["last_holdout_loss"] = measured
                    state["holdout_evaluated_successful_total"] = state["successful_total"]
                    if measured > state["initial_holdout_loss"] * 1.05 + 0.01:
                        reason = "HOLD_STUDENT_HOLDOUT_REGRESSION"
                checkpoint, record = save_checkpoint(output, model, optimizer, scheduler, scaler, state, lineage, torch)
                last_save = time.monotonic()
                if reason:
                    break
            atomic_json(output / "owner_progress.json", {"state": "NATIVE_STUDENT_UPDATE_OBSERVED",
                        "successful_optimizer_steps": state["successful_total"], "attempted_steps": state["attempted_total"],
                        "skipped_steps": state["skipped_total"], "adapter_tensor_sha256": before_hash,
                        "loss": proof["loss"], "pid": os.getpid(), "time": time.time()})
        # A STOP seen before the next update must still persist completed progress.
        if checkpoint is None or read_json(checkpoint / "student_state.json") != state:
            checkpoint, record = save_checkpoint(output, model, optimizer, scheduler, scaler, state, lineage, torch)
        holdout_current = state["holdout_evaluated_successful_total"] == state["successful_total"]
        holdout_ok = holdout_current and state["last_holdout_loss"] <= state["initial_holdout_loss"] * 1.05 + 0.01
        receipt = {"schema": PROOF_SCHEMA, "state": reason or ("STUDENT_RESTART_AND_UPDATES_VERIFIED" if restart_verified
                   else "STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED"),
                   "lineage_sha256": canonical_sha(lineage), "base_manifest_sha256": MANIFEST_SHA,
                   "successful_optimizer_steps": state["successful_total"],
                   "new_successful_optimizer_steps": state["successful_total"] - start_success,
                   "attempted_steps": state["attempted_total"], "skipped_steps": state["skipped_total"],
                   "update_evidence": state["update_evidence"], "final_adapter_tensor_sha256": adapter_hash(model, torch),
                   "checkpoint": str(checkpoint), "checkpoint_manifest_sha256": sha256_file(checkpoint / "checkpoint_manifest.json"),
                   "reload_verified": restart_verified,
                   "holdout_finite": holdout_current and math.isfinite(state["last_holdout_loss"]),
                   "holdout_evaluated_successful_total": state["holdout_evaluated_successful_total"],
                   "independent_holdout_accepted": holdout_ok, "holdout_scope": "DISJOINT_NEXT_TOKEN_LOSS_NOT_GENERAL_IQ",
                   "initial_holdout_loss": state["initial_holdout_loss"], "final_holdout_loss": state["last_holdout_loss"],
                   "runtime": observed, "kernel_smoke": smoke, "base_staging": staging,
                   "dataset_provenance_manifest_sha256": args.dataset_manifest_sha256,
                   "training_unique_examples": len(train), "holdout_unique_examples": len(holdout),
                   "process_identity": process_identity(),
                   "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                   "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                   "active_chat_changed": False, "old_optimizer_loaded": False,
                   "manual_stop_cleared": False, "continuous_resume_authorized_by_receipt": False}
        atomic_json(output / "owner_last_result.json", receipt)
        if restart_verified and holdout_ok and not reason and state["successful_total"] >= 6:
            verify_proof(receipt, lineage=lineage, minimum_updates=6)
            certificate_path = output / "owner_acceptance.json"
            if not certificate_path.exists():
                # This durable first acceptance does not get replaced by a
                # later cooperative pause whose holdout evaluation is pending.
                atomic_json(certificate_path, receipt, replace=False)
        print(json.dumps({k: receipt[k] for k in ("state", "successful_optimizer_steps", "new_successful_optimizer_steps",
                         "attempted_steps", "skipped_steps", "reload_verified", "independent_holdout_accepted")}), flush=True)
        # Exiting this sole trainer process releases CUDA allocations. The native
        # supervisor/dispatcher must read back PID/VRAM before giving chat its lease.
        return 0 if reason is None else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--base-directory", required=True, type=Path)
    parser.add_argument("--base-transport", choices=("regular-files", "sealed-memfd"), required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--train-jsonl", required=True, type=Path)
    parser.add_argument("--train-sha256", required=True)
    parser.add_argument("--holdout-jsonl", required=True, type=Path)
    parser.add_argument("--holdout-sha256", required=True)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--dataset-manifest-sha256", required=True)
    parser.add_argument("--successful-updates", required=True, type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{1,24}", args.request):
        raise Hold("HOLD_OWNER_REQUEST_ID")
    return run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Hold as exc:
        print(json.dumps({"state": str(exc), "native_success_claimed": False}), flush=True)
        raise SystemExit(2)
