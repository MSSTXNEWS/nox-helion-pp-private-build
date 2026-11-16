#!/usr/bin/env python3
"""Bounded diagnostic in the existing trainer's lease; no weights or installs.

Only an exact known automatic AMP failure hold may remain during this tiny
diagnostic. Manual STOP and pause always block. No flag or service is changed.
The caller must pin this file and its two helper sources before native use.
"""
from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path("/root/nox")
SERVICE = "nox-train-volta-t866u"
MANUAL_STOPS = tuple(ROOT / p for p in (
    "STOP", "STOP.flag", "stop.flag", ".stop", "state/STOP", "program/STOP")) + (Path("/workspace/NOX_STOP"),)
HOLD = ROOT / "state/TRAIN_HOLD.flag"
PAUSE = ROOT / "state/TRAIN_PAUSE_REQUEST.flag"
STOPPED = False
REQUIRED_PACKAGE_VERSIONS = {
    "transformers": "5.23.0", "peft": "0.21.3", "accelerate": "1.15.0",
    "bitsandbytes": "0.50.2", "tokenizers": "0.23.3", "safetensors": "0.8.0",
}


class Hold(RuntimeError):
    pass


def sha256_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise Hold("HOLD_SMOKE_SMALL_SOURCE_PATH")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_environment(observed):
    if (observed["python_version"] != [3, 12, 16]
            or observed["torch_version"] != "2.6.0+cu124" or observed["torch_cuda"] != "12.4"
            or "sm_70" not in observed["torch_arch_list"]
            or observed["device_capability"] != [7, 0]
            or observed["packages"] != REQUIRED_PACKAGE_VERSIONS
            or observed["optional_fast_kernels_present"]):
        raise Hold("HOLD_RUNTIME_DRIFT_FROM_NATIVE_PROBE")


def tiny_safetensors_smoke(parent):
    import numpy as np
    import safetensors
    from safetensors import safe_open
    from safetensors.numpy import save
    expected = np.arange(6, dtype=np.float32).reshape(2, 3)
    raw = save({"probe": expected})
    fd = os.memfd_create("nox-qwen-tiny-smoke", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    path = Path(parent) / "probe.safetensors"
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise Hold("HOLD_MEMFD_TINY_WRITE")
            view = view[written:]
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), 15)
        if fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034)) & 15 != 15:
            raise Hold("HOLD_MEMFD_TINY_SEAL")
        path.symlink_to(f"/proc/{os.getpid()}/fd/{fd}")
        with safe_open(str(path), framework="numpy", device="cpu") as handle:
            actual = handle.get_tensor("probe")
            if not np.array_equal(actual, expected):
                raise Hold("HOLD_MEMFD_TINY_TENSOR")
        try:
            os.pwrite(fd, b"x", 0)
        except OSError as exc:
            if exc.errno != errno.EPERM:
                raise
        else:
            raise Hold("HOLD_MEMFD_TINY_WRITE_NOT_BLOCKED")
        return {"state": "REAL_SAFETENSORS_MEMFD_READ_AND_SEAL_VERIFIED",
                "safetensors_version": safetensors.__version__, "bytes": len(raw),
                "tensor_exact": True, "writes_rejected": True, "full_model_loaded": False}
    finally:
        if path.is_symlink() and os.readlink(path) == f"/proc/{os.getpid()}/fd/{fd}":
            path.unlink()
        os.close(fd)


def signal_stop(*_):
    global STOPPED
    STOPPED = True


def guard(expected_hold_sha, expected_hold_request):
    if STOPPED or any(p.exists() or p.is_symlink() for p in MANUAL_STOPS):
        raise Hold("HOLD_MANUAL_OWNER_STOP_OR_SIGNAL")
    if PAUSE.exists() or PAUSE.is_symlink():
        raise Hold("HOLD_EXISTING_TRAINING_PAUSE")
    if HOLD.exists() or HOLD.is_symlink():
        expected = ("OWNER_HYBRID_FAILED request=" + (expected_hold_request or "") + "\n").encode()
        if (HOLD.is_symlink() or not expected_hold_sha
                or not re.fullmatch(r"\d{1,24}", expected_hold_request or "")
                or HOLD.stat().st_size != len(expected)
                or HOLD.read_bytes() != expected
                or sha256_file(HOLD) != expected_hold_sha):
            raise Hold("HOLD_UNCLASSIFIED_OR_CHANGED_TRAIN_HOLD")
    elif expected_hold_sha:
        raise Hold("HOLD_AUTOMATIC_HOLD_DISAPPEARED")


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    if len(p.stdout) > 64 * 1024 or len(p.stderr) > 16 * 1024:
        raise Hold("HOLD_SMOKE_COMMAND_OUTPUT_BUDGET")
    return p


def inactive_trainer():
    p = command(["supervisorctl", "status", SERVICE])
    fields = p.stdout.strip().split()
    if (p.returncode not in (0, 3) or len(fields) < 2 or fields[0] != SERVICE
            or fields[1] not in {"STOPPED", "FATAL", "EXITED"}):
        raise Hold("HOLD_EXISTING_TRAINER_NOT_INACTIVE")
    return fields[1]


def gpu_admission():
    p = command(["nvidia-smi", "--query-gpu=index,uuid,memory.free", "--format=csv,noheader,nounits"])
    if p.returncode:
        raise Hold("HOLD_GPU_TELEMETRY")
    matches = [x.split(",") for x in p.stdout.splitlines() if x.split(",")[0].strip() == "1"]
    if len(matches) != 1 or len(matches[0]) != 3:
        raise Hold("HOLD_PHYSICAL_GPU1_TELEMETRY")
    gpu = [s.strip() for s in matches[0]]
    if int(gpu[2]) < 28 * 1024:
        raise Hold("HOLD_GPU1_FREE_MEMORY")
    p = command(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"])
    if p.returncode:
        raise Hold("HOLD_GPU_PROCESS_TELEMETRY")
    residents = []
    for row in p.stdout.splitlines():
        parts = [s.strip() for s in row.split(",")]
        if parts and parts[0] == gpu[1]:
            if len(parts) != 3 or not parts[1].isdigit():
                raise Hold("HOLD_GPU_PROCESS_TELEMETRY_SCHEMA")
            residents.append({"pid": int(parts[1]),
                              "used_mib": int(parts[2]) if parts[2].isdigit() else None})
    return {"physical_gpu": 1, "free_mib_before": int(gpu[2]),
            "existing_compute_residents": residents,
            "scope": "TINY_DIAGNOSTIC_5_PERCENT_ALLOCATOR_CAP_NOT_FULL_MODEL_ADMISSION"}


def run(expected_hold_sha, expected_hold_request):
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "1" or os.environ.get("BNB_CUDA_VERSION"):
        raise Hold("HOLD_SINGLE_GPU1_OR_BNB_OVERRIDE")
    if Path(sys.executable).absolute() != Path("/root/venv_volta/bin/python"):
        raise Hold("HOLD_EXISTING_VOLTA_PYTHON_REQUIRED")
    signal.signal(signal.SIGTERM, signal_stop); signal.signal(signal.SIGINT, signal_stop)
    guard(expected_hold_sha, expected_hold_request)
    lease = os.open(ROOT / "state/forge_training.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    # Do not explicitly close the lease before process exit; CUDA teardown and
    # the kernel lease lifetime end together even on a Python exception.
    try:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise Hold("HOLD_EXISTING_TRAINER_WRITER_ACTIVE") from exc
    trainer_state = inactive_trainer()
    gpu = gpu_admission()
    guard(expected_hold_sha, expected_hold_request)
    os.environ.update(USE_HUB_KERNELS="NO", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4")
    import torch
    import bitsandbytes as bnb
    from transformers import Qwen3_5ForConditionalGeneration
    from peft import LoraConfig
    observed = {"python_version": list(sys.version_info[:3]), "torch_version": torch.__version__,
                "torch_cuda": torch.version.cuda, "torch_arch_list": torch.cuda.get_arch_list(),
                "device_capability": list(torch.cuda.get_device_capability(0)),
                "packages": {n: importlib.metadata.version(n) for n in REQUIRED_PACKAGE_VERSIONS},
                "optional_fast_kernels_present": [n for n in ("flash_attn", "fla", "causal_conv1d", "liger_kernel")
                                                    if importlib.util.find_spec(n) is not None]}
    validate_environment(observed)
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise Hold("HOLD_ONE_VISIBLE_GPU_REQUIRED")
    torch.set_num_threads(4); torch.manual_seed(42)
    torch.cuda.set_per_process_memory_fraction(0.05, 0)
    with tempfile.TemporaryDirectory(prefix="nox-qwen-smoke-") as parent:
        memfd = tiny_safetensors_smoke(parent)
    guard(expected_hold_sha, expected_hold_request)
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
    torch.cuda.synchronize()
    guard(expected_hold_sha, expected_hold_request)
    inactive_trainer()
    return {"schema": "NOX_QWEN35_RUNTIME_SMOKE_V1", "state": "NATIVE_RUNTIME_SMOKE_PASSED",
            "time": time.time(), "pid": os.getpid(), "runtime": observed, "gpu": gpu,
            "initial_trainer_state": trainer_state, "memfd": memfd,
            "fp16_matmul_backward": True, "nf4_input_backward": True,
            "qwen_builtin_class_imported": Qwen3_5ForConditionalGeneration.__name__,
            "peft_builtin_class_imported": LoraConfig.__name__,
            "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(),
            "hold_preserved_sha256": expected_hold_sha or None,
            "full_model_loaded": False, "optimizer_updates_proven": False,
            "install_performed": False, "services_modified": False,
            "manual_stop_cleared": False,
            "source_sha256": sha256_file(__file__)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-auto-hold-sha256")
    parser.add_argument("--expected-auto-hold-request")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.expected_auto_hold_sha256, args.expected_auto_hold_request), sort_keys=True), flush=True)
    except Hold as exc:
        print(json.dumps({"state": str(exc), "native_success_claimed": False}), flush=True)
        raise SystemExit(2)
