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
import re
import subprocess
import platform
import sys
from pathlib import Path
import train_qlora


PACKAGES = (
    "torch", "transformers", "peft", "trl", "accelerate",
    "datasets", "bitsandbytes", "safetensors"
)


def _require_cuda_parent_selection_compatible(chosen_uuid: str) -> None:
    """Inherited CUDA device selection must not silently select another GPU.

    Source-only preflight may choose a UUID only if no conflicting parent
    CUDA mask/order was already installed; it does not attest real GPU binding.
    """
    inherited_visibility = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited_visibility is not None and inherited_visibility != chosen_uuid:
        raise RuntimeError("CUDA_PARENT_VISIBLE_DEVICES_CONFLICT")
    inherited_order = os.environ.get("CUDA_DEVICE_ORDER")
    if inherited_order is not None and inherited_order != "PCI_BUS_ID":
        raise RuntimeError("CUDA_PARENT_DEVICE_ORDER_CONFLICT")



# A CUDA check must not leave imported torch/CUDA state in the loader process.
# The child is one-shot, shell-free, and receives only a copied CUDA selection.
_CUDA_PROBE_CHILD = r"""
import json
import re
try:
    import torch
    cuda_build = getattr(getattr(torch, "version", None), "cuda", None)
    if not isinstance(cuda_build, str) or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}", cuda_build):
        result = {"error": "TORCH_CUDA_BUILD_NOT_CONFIRMED"}
    elif not torch.cuda.is_available():
        result = {"error": "TORCH_CUDA_RUNTIME_UNAVAILABLE"}
    else:
        count = torch.cuda.device_count()
        if type(count) is not int or count != 1:
            result = {"error": "CUDA_VISIBLE_DEVICE_COUNT_NOT_ONE"}
        else:
            result = {"cuda_runtime": cuda_build, "cuda_device_count": 1}
except Exception:
    result = {"error": "TORCH_CUDA_RUNTIME_UNAVAILABLE"}
print(json.dumps(result, separators=(",", ":")))
"""


def _run_cuda_probe_isolated(uuid: str) -> dict:
    """Inspect a UUID-scoped CUDA device in a fresh, short-lived interpreter.

    This is runtime telemetry only, not real training, model rights or wheel SHA.
    The loader process does not import torch or edit its own CUDA variables.
    """
    if not isinstance(uuid, str) or re.fullmatch(
        r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", uuid
    ) is None:
        raise RuntimeError("GPU_UUID_INVALID")
    _require_cuda_parent_selection_compatible(uuid)
    child_env = os.environ.copy()
    # Check the actual copy, not only the earlier mutable parent snapshot.
    if child_env.get("CUDA_VISIBLE_DEVICES") not in (None, uuid):
        raise RuntimeError("CUDA_PARENT_VISIBLE_DEVICES_CONFLICT")
    if child_env.get("CUDA_DEVICE_ORDER") not in (None, "PCI_BUS_ID"):
        raise RuntimeError("CUDA_PARENT_DEVICE_ORDER_CONFLICT")
    child_env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    child_env["CUDA_VISIBLE_DEVICES"] = uuid
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _CUDA_PROBE_CHILD],
            env=child_env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="strict", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise RuntimeError("TORCH_CUDA_ISOLATED_PROCESS_FAILED") from None
    if (type(result.returncode) is not int or result.returncode != 0
            or not isinstance(result.stdout, str) or not 0 < len(result.stdout) <= 4096):
        raise RuntimeError("TORCH_CUDA_ISOLATED_PROCESS_FAILED")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("TORCH_CUDA_ISOLATED_RESPONSE_INVALID") from None
    known_errors = {
        "TORCH_CUDA_BUILD_NOT_CONFIRMED",
        "TORCH_CUDA_RUNTIME_UNAVAILABLE",
        "CUDA_VISIBLE_DEVICE_COUNT_NOT_ONE",
    }
    if not isinstance(payload, dict):
        raise RuntimeError("TORCH_CUDA_ISOLATED_RESPONSE_INVALID")
    if set(payload) == {"error"} and payload["error"] in known_errors:
        raise RuntimeError(payload["error"])
    if (set(payload) != {"cuda_runtime", "cuda_device_count"}
            or not isinstance(payload["cuda_runtime"], str)
            or re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}", payload["cuda_runtime"]) is None
            or type(payload["cuda_device_count"]) is not int
            or payload["cuda_device_count"] != 1):
        raise RuntimeError("TORCH_CUDA_ISOLATED_RESPONSE_INVALID")
    return payload


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
        "model_license_verified": False,
        "dataset_rights_verified": False,
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
        limit = {"ECO": 80, "BALANCED": 83, "INTENSIVE": 85}[profile]
        if temperature >= limit:
            raise RuntimeError("GPU_THERMAL_HEADROOM_UNAVAILABLE")
        memory = train_qlora.gpu_vram_headroom(exe, selected["uuid"], profile)
        # Inventory and UUID-scoped telemetry must agree on physical VRAM;
        # a changed/MIG/driver view is not proof of the selected GPU budget.
        if (type(memory) is not dict or type(memory.get("total_mib")) is not int
                or memory["total_mib"] != int(selected["memory_total_mib"])):
            raise RuntimeError("GPU_TOTAL_MEMORY_SNAPSHOT_DRIFT")
        report["gpu"] = {
            "name": selected["name"], "uuid": selected["uuid"],
            "temperature_c": temperature, **memory
        }
    except (ValueError, OSError, RuntimeError) as exc:
        report["errors"].append(str(exc))
        return report

    if not any(x.startswith("PACKAGE_NOT_INSTALLED") for x in report["errors"]):
        try:
            report["gpu"].update(_run_cuda_probe_isolated(selected["uuid"]))
        except RuntimeError as exc:
            report["errors"].append(str(exc))
    report["status"] = "HARDWARE_READY_ONLY" if not report["errors"] else "HOLD"
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
    return 0 if report["status"] == "HARDWARE_READY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
