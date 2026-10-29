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


def _check_declared_versions(report: dict) -> None:
    """Reuse PyPA's parser for existing ranges; never resolve/install packages."""
    try:
        from packaging.requirements import Requirement
        from packaging.version import InvalidVersion, Version
    except ImportError:
        report["errors"].append("DEPENDENCY_REQUIREMENT_PARSER_UNAVAILABLE")
        return
    try:
        lines = Path(__file__).with_name("requirements-qlora.txt").read_text(encoding="utf-8").splitlines()
        requirements = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            item = Requirement(line)
            if (item.name in requirements or item.url or item.marker or item.extras
                    or not item.specifier):
                raise ValueError("unsupported dependency contract")
            requirements[item.name] = item
        if set(requirements) != set(PACKAGES):
            raise ValueError("dependency package contract mismatch")
    except (OSError, ValueError):
        report["errors"].append("DECLARED_DEPENDENCY_CONTRACT_UNAVAILABLE")
        return
    compatible = True
    for package, item in requirements.items():
        installed = report["packages"][package]
        installed["required"] = str(item.specifier)
        if installed["state"] != "INSTALLED":
            compatible = False
            continue
        try:
            matches = item.specifier.contains(Version(installed["version"]), prereleases=False)
        except InvalidVersion:
            installed["state"] = "INVALID"
            report["errors"].append("PACKAGE_METADATA_INVALID:" + package)
            compatible = False
            continue
        if not matches:
            installed["state"] = "INCOMPATIBLE"
            report["errors"].append("PACKAGE_VERSION_OUT_OF_RANGE:" + package)
            compatible = False
    if compatible:
        report["dependency_status"] = "RANGE_CHECK_PASSED"


def inspect(profile: str, gpu_index: int) -> dict:
    """Inspect in a dedicated worker process; CUDA state is process-global."""
    report = {
        "schema": "NOX-P04-LOCAL-GPU-PREFLIGHT-v1",
        "status": "HOLD",
        "profile": profile,
        "gpu_index": gpu_index,
        "platform": platform.system(),
        "python": platform.python_version(),
        "packages": {},
        "dependency_status": "HOLD",
        "dependency_lock_verified": False,
        "runtime_compatibility_verified": False,
        "gpu": None,
        "errors": [],
        "runtime_training_verified": False,
        "model_license_verified": False,
        "dataset_rights_verified": False,
    }
    # The installer can call this function directly; argparse validation only
    # protects the CLI. Reject bad persisted settings before vendor discovery.
    if not isinstance(profile, str) or profile not in train_qlora.PROFILES:
        report["errors"].append("GPU_PROFILE_INVALID")
    if type(gpu_index) is not int or gpu_index < 0:
        report["errors"].append("GPU_INDEX_INVALID")
    if report["errors"]:
        return report
    for package in PACKAGES:
        try:
            version = metadata.version(package)
            if not isinstance(version, str) or not version.strip():
                raise ValueError("PACKAGE_VERSION_METADATA_INVALID")
            report["packages"][package] = {"state": "INSTALLED", "version": version}
        except metadata.PackageNotFoundError:
            report["packages"][package] = {"state": "MISSING", "version": None}
            report["errors"].append("PACKAGE_NOT_INSTALLED:" + package)
        except (ValueError, OSError):
            report["packages"][package] = {"state": "INVALID", "version": None}
            report["errors"].append("PACKAGE_METADATA_INVALID:" + package)

    _check_declared_versions(report)
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
        report["gpu"] = {
            "name": selected["name"], "uuid": selected["uuid"],
            "temperature_c": temperature, **memory
        }
    except (ValueError, OSError, RuntimeError) as exc:
        report["errors"].append(str(exc))
        return report

    if not report["errors"]:
        # This proves local package installations, not CUDA runtime functionality.
        cuda_environment = {name: os.environ.get(name) for name in
                            ("CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES")}
        try:
            # A previously initialized runtime cannot be rebound by rewriting
            # environment variables; one visible device may be the wrong GPU.
            loaded_torch = sys.modules.get("torch")
            if loaded_torch is not None and loaded_torch.cuda.is_initialized():
                report["errors"].append("CUDA_PREFLIGHT_FRESH_PROCESS_REQUIRED")
                return report
            # Match training's single approved UUID before importing CUDA.
            os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            os.environ["CUDA_VISIBLE_DEVICES"] = selected["uuid"]
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
        finally:
            # Do not leave the installer's later worker launches pinned to this
            # probe's selection, including failure/HOLD paths.
            for name, original in cuda_environment.items():
                if original is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = original
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
