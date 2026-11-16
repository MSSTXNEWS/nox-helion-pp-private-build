"""Read-only attestation for the pinned CUDA/SM70 Maya executable.

This inspects files and embedded cubins only. It never starts Maya or creates a CUDA context.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

PINNED_BINARY_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
EXPECTED_CUDA_ARCHITECTURES = "70"
SM70_ELF = re.compile(r"\bsm_70\b")


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return True
    return False


def _read_regular(path: Path) -> bytes:
    if _has_symlink_component(path):
        raise OSError("HOLD_MAYA_BINARY_PATH_SYMLINK")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("HOLD_MAYA_BINARY_INPUT_NOT_REGULAR")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        named = path.lstat()
        identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
        if (not stat.S_ISREG(named.st_mode) or identity(before) != identity(after)
                or identity(before) != identity(named)):
            raise OSError("HOLD_MAYA_BINARY_CHANGED_DURING_READ")
        return data
    finally:
        os.close(fd)


def attest_maya_binary(binary_path: str | os.PathLike[str],
                       expected_sha256: str = PINNED_BINARY_SHA256) -> dict:
    """Require actual binary bytes, CMake architecture, and embedded SM70 ELF evidence."""
    try:
        binary = Path(binary_path).absolute()
        if _has_symlink_component(binary):
            return {"state": "HOLD_MAYA_BINARY_PATH_SYMLINK"}
        binary_bytes = _read_regular(binary)
        actual_sha256 = hashlib.sha256(binary_bytes).hexdigest()
        if actual_sha256 != expected_sha256 or expected_sha256 != PINNED_BINARY_SHA256:
            return {"state": "HOLD_MAYA_BINARY_SHA256"}
        cache = binary.parent / "CMakeCache.txt"
        cache_text = _read_regular(cache).decode("utf-8")
        arch = re.findall(r"^CMAKE_CUDA_ARCHITECTURES(?::[^=]+)?=(.*)$", cache_text, re.MULTILINE)
        if len(arch) != 1 or arch[0].strip() != EXPECTED_CUDA_ARCHITECTURES:
            return {"state": "HOLD_MAYA_CMAKE_CUDA_ARCHITECTURES",
                    "expected": EXPECTED_CUDA_ARCHITECTURES}
        inspector = shutil.which("cuobjdump")
        if not inspector:
            return {"state": "HOLD_MAYA_CUOBJDUMP_UNAVAILABLE"}
        try:
            result = subprocess.run([inspector, "--list-elf", str(binary)], capture_output=True,
                                    text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {"state": "HOLD_MAYA_ELF_INSPECTION_FAILED"}
        if result.returncode != 0:
            return {"state": "HOLD_MAYA_ELF_INSPECTION_FAILED"}
        elf_report = (result.stdout or "") + "\n" + (result.stderr or "")
        if not SM70_ELF.search(elf_report):
            return {"state": "HOLD_MAYA_SM70_ELF_MISSING"}
        return {
            "state": "BINARY_BUILD_ATTESTED_SOURCE_ONLY",
            "binary_sha256": actual_sha256,
            "cuda_architectures": arch[0].strip(),
            "embedded_sm70_elf": True,
            "measured": False,
        }
    except OSError as exc:
        reason = str(exc)
        if reason.startswith("HOLD_MAYA_"):
            return {"state": reason}
        return {"state": "HOLD_MAYA_BINARY_UNREADABLE"}
    except (UnicodeError, ValueError):
        return {"state": "HOLD_MAYA_BINARY_BUILD_METADATA_INVALID"}
