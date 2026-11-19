#!/usr/bin/env python3
"""Stage one owner credential through an exclusive, no-follow file creation."""
from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path


def create_secret_file(runner_temp: str | os.PathLike[str], path: str | os.PathLike[str], secret: str) -> None:
    """Create a private single-use secret file without following/replacing entries."""
    temp = Path(runner_temp)
    target = Path(path)
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[0-9]{1,20}", run_id) or not re.fullmatch(r"[0-9]{1,8}", attempt):
        raise RuntimeError("HOLD_RUNNER_TEMP_ID")
    expected = temp / f"nox2-s03-{run_id}-{attempt}"
    if not temp.is_absolute() or target != expected:
        raise RuntimeError("HOLD_RUNNER_TEMP_PATH")
    if not isinstance(secret, str) or not secret or len(secret) > 4096:
        raise RuntimeError("HOLD_CREDENTIAL_FORMAT")
    try:
        raw = secret.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeError("HOLD_CREDENTIAL_FORMAT") from None
    if any(byte < 0x21 or byte > 0x7e for byte in raw):
        raise RuntimeError("HOLD_CREDENTIAL_FORMAT")

    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("HOLD_NOFOLLOW_UNAVAILABLE")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dir_flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        dir_fd = os.open(temp, dir_flags)
    except OSError:
        raise RuntimeError("HOLD_RUNNER_TEMP_DIRECTORY") from None
    file_fd = None
    created_stat = None
    try:
        directory_stat = os.fstat(dir_fd)
        if (not stat.S_ISDIR(directory_stat.st_mode)
                or directory_stat.st_uid != os.geteuid()
                or directory_stat.st_mode & 0o022):
            raise RuntimeError("HOLD_RUNNER_TEMP_DIRECTORY")
        name = expected.name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            file_fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
        except FileExistsError:
            raise RuntimeError("HOLD_CREDENTIAL_PATH_EXISTS") from None
        except OSError:
            raise RuntimeError("HOLD_CREDENTIAL_CREATE") from None
        created_stat = os.fstat(file_fd)
        if (not stat.S_ISREG(created_stat.st_mode) or created_stat.st_nlink != 1
                or created_stat.st_uid != os.geteuid()):
            raise RuntimeError("HOLD_CREDENTIAL_FILE_TYPE")
        os.fchmod(file_fd, 0o600)
        if stat.S_IMODE(os.fstat(file_fd).st_mode) != 0o600:
            raise RuntimeError("HOLD_CREDENTIAL_FILE_MODE")
        offset = 0
        while offset < len(raw):
            offset += os.write(file_fd, raw[offset:])
        os.fsync(file_fd)
        final_stat = os.fstat(file_fd)
        if final_stat.st_size != len(raw) or final_stat.st_nlink != 1:
            raise RuntimeError("HOLD_CREDENTIAL_FILE_WRITE")
    except Exception:
        if file_fd is not None and created_stat is not None:
            try:
                current = os.stat(expected.name, dir_fd=dir_fd, follow_symlinks=False)
                if (stat.S_ISREG(current.st_mode) and current.st_dev == created_stat.st_dev
                        and current.st_ino == created_stat.st_ino):
                    os.unlink(expected.name, dir_fd=dir_fd)
            except OSError:
                pass
        raise
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(dir_fd)


def main() -> int:
    temp = os.environ.get("RUNNER_TEMP", "")
    target = os.environ.get("NOX2_FILE", "")
    secret = os.environ.get("NOX2", "")
    try:
        create_secret_file(temp, target, secret)
    except Exception as exc:
        code = str(exc)
        print("NOX_OWNER_CREDENTIAL=" + (code if re.fullmatch(r"HOLD_[A-Z0-9_]+", code)
                                          else "HOLD_STAGE"), flush=True)
        return 2
    os.environ.pop("NOX2", None)
    print("NOX_OWNER_CREDENTIAL=STAGED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
