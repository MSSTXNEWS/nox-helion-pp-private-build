"""Read-only dynamic-linkage inspection for the pinned Maya ELF.

Only the system readelf utility is run. The Maya executable is never invoked;
there is no CUDA context, model load, pack, write, or service start.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def read_elf_linkage(binary: Path, pinned_sha256: str, sha_reader) -> dict:
    binary = Path(binary)
    result = {
        "schema": "NOX_MAYA_ELF_LINKAGE_READONLY_V1",
        "path": str(binary),
        "pinned_sha256": pinned_sha256,
        "state": "HOLD_UNKNOWN",
        "needed_sonames": [],
        "rpath": [],
        "cuda_driver_needed": False,
        "cuda_runtime_needed": False,
        "cublas_needed": False,
        "maya_executable_invoked": False,
        "cuda_context_created": False,
    }
    # Reuse the no-follow pinned-file hash check before giving the path to readelf.
    pin = sha_reader()
    result["observed_sha256"] = pin.get("observed_sha256")
    result["bytes"] = pin.get("bytes")
    if pin.get("state") != "SHA_PIN_MATCH_ELF_ONLY":
        result["state"] = "HOLD_BINARY_PIN"
        return result
    readelf = shutil.which("readelf")
    if not readelf:
        result["state"] = "HOLD_READELF_UNAVAILABLE"
        return result
    try:
        completed = subprocess.run(
            [readelf, "-d", "--wide", str(binary)],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        result["state"] = "HOLD_READELF_FAILED"
        return result
    if completed.returncode != 0:
        result["state"] = "HOLD_READELF_FAILED"
        return result
    needed = re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", completed.stdout)
    paths = re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^\]]*)\]", completed.stdout)
    result["needed_sonames"] = needed[:128]
    result["rpath"] = paths[:8]
    result["cuda_driver_needed"] = any(x.startswith("libcuda.so") for x in needed)
    result["cuda_runtime_needed"] = any(x.startswith("libcudart.so") for x in needed)
    result["cublas_needed"] = any(x.startswith(("libcublas.so", "libcublasLt.so")) for x in needed)
    result["state"] = "ELF_LINKAGE_READ_ONLY"
    return result
