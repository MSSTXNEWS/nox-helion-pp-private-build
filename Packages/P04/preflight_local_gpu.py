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
import re
import sys
from pathlib import Path
import train_qlora


PACKAGES = (
    "torch", "transformers", "peft", "trl", "accelerate",
    "datasets", "bitsandbytes", "safetensors"
)


def _check_pypa_wheel_abi(report: dict) -> None:
    """Check installed root package ranges and WHEEL tags; never install/resolve.

    Compatible local metadata is not a hashed wheel lock or CUDA binary proof.
    """
    try:
        from email.parser import Parser
        from packaging.requirements import Requirement
        from packaging.tags import parse_tag, sys_tags
        from packaging.utils import canonicalize_name
        from packaging.version import Version
    except ImportError:
        report["errors"].append("PYPA_WHEEL_ABI_PARSER_UNAVAILABLE")
        return
    try:
        requirements = {}
        for raw in Path(__file__).with_name("requirements-qlora.txt").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            requirement = Requirement(line)
            name = canonicalize_name(requirement.name)
            if (name in requirements or requirement.url or requirement.extras
                    or requirement.marker or not requirement.specifier):
                raise ValueError("unsupported requirement")
            requirements[name] = requirement
        if set(requirements) != set(PACKAGES):
            raise ValueError("incomplete root requirements")
        supported = set(sys_tags())
        if not supported:
            raise ValueError("no interpreter tags")
    except (OSError, UnicodeError, ValueError, TypeError):
        report["errors"].append("PYPA_DECLARED_ABI_CONTRACT_INVALID")
        return
    for package in PACKAGES:
        if report["packages"][package]["state"] != "INSTALLED":
            continue
        try:
            installed = Version(report["packages"][package]["version"])
            if not requirements[package].specifier.contains(installed, prereleases=False):
                report["errors"].append("PACKAGE_VERSION_OUT_OF_RANGE:" + package)
                continue
            wheel_text = metadata.distribution(package).read_text("WHEEL")
            if not isinstance(wheel_text, str) or not 0 < len(wheel_text) <= 65536:
                raise ValueError("missing or oversized WHEEL")
            wheel = Parser().parsestr(wheel_text)
            versions = wheel.get_all("Wheel-Version", [])
            tags = wheel.get_all("Tag", [])
            if len(versions) != 1 or versions[0] not in ("1.0", "1.1") or not 1 <= len(tags) <= 128:
                raise ValueError("ambiguous WHEEL headers")
            wheel_tags = set()
            for tag in tags:
                if not isinstance(tag, str) or len(tag) > 256:
                    raise ValueError("invalid wheel tag")
                wheel_tags.update(parse_tag(tag))
            if not wheel_tags:
                raise ValueError("empty wheel tags")
            compatible_tags = wheel_tags.intersection(supported)
            if not compatible_tags:
                report["errors"].append("WHEEL_ABI_TAG_MISMATCH:" + package)
            elif package in ("torch", "bitsandbytes") and not any(
                tag.platform == "win_amd64" for tag in compatible_tags
            ):
                # GPU-critical binary dependencies must expose an installed
                # Windows AMD64 wheel, not merely a universal py3-none-any
                # tag. This remains metadata-only: no CUDA/driver proof.
                report["errors"].append("GPU_NATIVE_WIN_AMD64_WHEEL_REQUIRED:" + package)
        except (ValueError, TypeError, OSError, metadata.PackageNotFoundError):
            report["errors"].append("WHEEL_METADATA_INVALID:" + package)
    if not report["errors"]:
        report["wheel_abi_status"] = "INSTALLED_ROOT_TAG_MATCH_ONLY"


def _validate_gpu_memory_snapshot(selected: dict, memory: dict) -> None:
    """Reject inconsistent NVIDIA inventory/VRAM reads before importing CUDA.

    Memory telemetry is a separate nvidia-smi query; a changed total or
    malformed headroom response cannot attest the selected physical GPU.
    """
    raw_total = selected.get("memory_total_mib")
    if not isinstance(raw_total, str) or re.fullmatch(r"[0-9]{1,9}", raw_total) is None:
        raise RuntimeError("GPU_VRAM_TELEMETRY_CONTRACT_INVALID")
    inventory_total = int(raw_total)
    required = ("free_mib", "total_mib", "gui_reserve_mib")
    if not isinstance(memory, dict) or any(type(memory.get(k)) is not int for k in required):
        raise RuntimeError("GPU_VRAM_TELEMETRY_CONTRACT_INVALID")
    free, total, reserve = (memory[k] for k in required)
    if not (1 <= inventory_total <= 1024 * 1024 and
            1 <= total <= 1024 * 1024 and
            0 <= free <= total and
            1024 <= reserve < total and
            free >= reserve + 1024):
        raise RuntimeError("GPU_VRAM_TELEMETRY_CONTRACT_INVALID")
    if total != inventory_total:
        raise RuntimeError("GPU_INVENTORY_VRAM_TOTAL_MISMATCH")


def _require_gpu_identity_stable(identity: tuple[str, str, str], original: dict, latest: list[dict]) -> None:
    """Reject re-enumerated or mutated selected GPU before CUDA selection.

    This is a second inventory observation, not an atomic hardware lock.
    """
    if not isinstance(latest, list) or not isinstance(original, dict):
        raise RuntimeError("GPU_SELECTION_CHANGED_DURING_PREFLIGHT")
    selected = [item for item in latest if isinstance(item, dict) and item.get("index") == identity[0]]
    if (len(selected) != 1
            or tuple(original.get(key) for key in ("index", "uuid", "memory_total_mib")) != identity
            or tuple(selected[0].get(key) for key in ("index", "uuid", "memory_total_mib")) != identity):
        raise RuntimeError("GPU_SELECTION_CHANGED_DURING_PREFLIGHT")


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


def inspect(profile: str, gpu_index: int) -> dict:
    report = {
        "schema": "NOX-P04-LOCAL-GPU-PREFLIGHT-v1",
        "status": "HOLD",
        "profile": profile,
        "gpu_index": gpu_index,
        "platform": platform.system(),
        "python": platform.python_version(),
        "packages": {},
        "wheel_abi_status": "HOLD",
        "dependency_lock_verified": False,
        "wheel_artifact_sha256_verified": False,
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
    # A Windows ARM/x86 or 32-bit Python worker must not advertise a CUDA
    # preflight for the target AMD64 PyTorch/bitsandbytes wheel environment.
    # This is an ABI admission guard, NOT proof of wheel or CUDA compatibility.
    if sys.maxsize <= (1 << 32) or platform.machine().lower() not in ("amd64", "x86_64"):
        report["errors"].append("WINDOWS_AMD64_64BIT_PYTHON_REQUIRED")
        return report
    if not report["errors"]:
        _check_pypa_wheel_abi(report)
    if report["errors"]:
        return report
    # UUID isolation must be established before any CUDA context exists.
    # Changing CUDA_VISIBLE_DEVICES cannot safely rebind an initialized one.
    preloaded_torch = sys.modules.get("torch")
    if preloaded_torch is not None:
        is_initialized = getattr(getattr(preloaded_torch, "cuda", None), "is_initialized", None)
        try:
            context_state = is_initialized() if callable(is_initialized) else None
        except Exception:
            context_state = None
        if context_state is not False:
            report["errors"].append("CUDA_CONTEXT_PREINITIALIZED_OR_UNVERIFIABLE")
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
        # Freeze the selected index/UUID/capacity BEFORE independent probes:
        # a mutable inventory row may be replaced or re-enumerated mid-check.
        identity = tuple(selected[key] for key in ("index", "uuid", "memory_total_mib"))
        temperature = train_qlora.gpu_temperature(exe, identity[1])
        limit = {"ECO": 80, "BALANCED": 83, "INTENSIVE": 85}[profile]
        if type(temperature) not in (int, float) or not 0 <= temperature:
            raise RuntimeError("GPU_TEMPERATURE_UNAVAILABLE")
        if temperature >= limit:
            raise RuntimeError("GPU_THERMAL_HEADROOM_UNAVAILABLE")
        memory = train_qlora.gpu_vram_headroom(exe, identity[1], profile)
        _validate_gpu_memory_snapshot(selected, memory)
        # nvidia-smi inventory and UUID-scoped telemetry are independent reads.
        # A second inventory check detects hotplug/reindex and in-place mutation
        # before reporting hardware readiness; it cannot lock future GPU state.
        _require_gpu_identity_stable(identity, selected, train_qlora.gpu_inventory(exe))
        # Parent CUDA visibility may have been pinned by the host/other worker;
        # silently replacing it could select a different physical device.
        _require_cuda_parent_selection_compatible(identity[1])
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
            # Match training's single approved UUID before importing CUDA.
            os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            os.environ["CUDA_VISIBLE_DEVICES"] = selected["uuid"]
            import torch
            cuda_build = getattr(getattr(torch, "version", None), "cuda", None)
            if not isinstance(cuda_build, str) or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}", cuda_build):
                report["errors"].append("TORCH_CUDA_BUILD_NOT_CONFIRMED")
            elif not torch.cuda.is_available():
                report["errors"].append("TORCH_CUDA_RUNTIME_UNAVAILABLE")
            else:
                report["gpu"]["cuda_runtime"] = cuda_build
                device_count = torch.cuda.device_count()
                report["gpu"]["cuda_device_count"] = device_count
                if device_count != 1:
                    report["errors"].append("CUDA_VISIBLE_DEVICE_COUNT_NOT_ONE")
        except Exception:
            report["errors"].append("TORCH_CUDA_RUNTIME_UNAVAILABLE")
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
