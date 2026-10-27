#!/usr/bin/env python3
"""Read-only NOX P04 preflight on the actual Windows GPU host.

No model download, no training, no API/network calls, no privilege escalation.
Exit 0 only when NVIDIA hardware and all local QLoRA prerequisites exist.
A green preflight NEVER means training/checkpoint/eval/merge was completed.
"""
from __future__ import annotations
import argparse
from importlib import metadata
import json
import os
import platform
import sys
from pathlib import Path
import train_qlora


PACKAGES = (
    "torch", "transformers", "peft", "trl", "accelerate",
    "datasets", "bitsandbytes", "safetensors"
)


def inspect(profile: str, gpu_index: int) -> dict:
    report = {
        "schema": "NOX-P04-LOCAL-GPU-PREFLIGHT-v1",
        "status": "HOLD",
        "profile": profile,
        "gpu_index": gpu_index,
        "platform": platform.system(),
        "python": platform.python_version(),
        "packages": {},
        "gpu": None,
        "errors": [],
        "runtime_training_verified": False,
    }
    for package in PACKAGES:
        try:
            version = metadata.version(package)
            report["packages"][package] = {"state": "INSTALLED", "version": version}
        except metadata.PackageNotFoundError:
            report["packages"][package] = {"state": "MISSING", "version": None}
            report["errors"].append("PACKAGE_NOT_INSTALLED:" + package)

    if platform.system() != "Windows":
        report["errors"].append("WINDOWS_GPU_HOST_REQUIRED")
        return report
    exe = train_qlora.nvidia_smi()
    if not exe:
        report["errors"].append("NVIDIA_TELEMETRY_UNAVAILABLE")
        return report
    try:
        devices = train_qlora.gpu_inventory(exe)
        selected = next((x for x in devices if int(x["index"]) == gpu_index), None)
        if not selected:
            raise RuntimeError("GPU_INDEX_NOT_FOUND")
        temperature = train_qlora.gpu_temperature(exe, selected["uuid"])
        if temperature is None:
            raise RuntimeError("GPU_TEMPERATURE_UNAVAILABLE")
        if temperature >= 80 if profile == "ECO" else temperature >= 83 if profile == "BALANCED" else temperature >= 85:
            raise RuntimeError("GPU_THERMAL_HEADROOM_UNAVAILABLE")
        memory = train_qlora.gpu_vram_headroom(exe, selected["uuid"], profile)
        report["gpu"] = {
            "name": selected["name"], "uuid": selected["uuid"],
            "temperature_c": temperature, **memory
        }
    except (ValueError, OSError, RuntimeError) as exc:
        report["errors"].append(str(exc))
        return report

    if not any(x.startswith("PACKAGE_NOT_INSTALLED") for x in report["errors"]):
        # This proves local package installations, not CUDA runtime functionality.
        try:
            import torch
            if not torch.cuda.is_available():
                report["errors"].append("TORCH_CUDA_RUNTIME_UNAVAILABLE")
            else:
                report["gpu"]["cuda_runtime"] = torch.version.cuda
                report["gpu"]["cuda_device_count"] = torch.cuda.device_count()
                if torch.cuda.device_count() != 1:
                    report["errors"].append("CUDA_VISIBLE_DEVICE_COUNT_NOT_ONE")
        except Exception:
            report["errors"].append("TORCH_CUDA_RUNTIME_UNAVAILABLE")
    report["status"] = "READY_FOR_AUTHORIZED_TRAINING" if not report["errors"] else "HOLD"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(train_qlora.PROFILES), default="BALANCED")
    parser.add_argument("--gpu-index", type=int, default=0)
    args = parser.parse_args()
    if args.gpu_index < 0:
        parser.error("GPU_INDEX_INVALID")
    report = inspect(args.profile, args.gpu_index)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "READY_FOR_AUTHORIZED_TRAINING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
