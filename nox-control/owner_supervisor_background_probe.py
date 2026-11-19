"""Bounded fixed Supervisor status and process memory reads."""

import os
import re
import stat
import subprocess
from pathlib import Path

PROC = Path("/proc")
CGROUP = Path("/sys/fs/cgroup")
BOOT = "9c0ecc02-85c1-452b-b8ae-521e9a11fd03"
SUPERVISOR = 114, 167791115
MODEL = "nox-ds41-8098", 3266857, 172046662
TARGETS = ()
STOP_TARGET = None


class Hold(RuntimeError):
    """A stable reason code suitable for the owner action receipt."""


def need(check, code):
    if not check:
        raise Hold(code)


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_ctime_ns)


def read(path, limit, *, rooted=False):
    if rooted:
        trusted_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        need(stat.S_ISREG(before.st_mode) and (not rooted or
             (before.st_uid == before.st_gid == 0 and not before.st_mode & 0o022
              and before.st_nlink == 1)), "FILE_IDENTITY")
        data = file.read(limit + 1)
        after = os.fstat(file.fileno())
    need(len(data) <= limit and stamp(before) == stamp(after) == stamp(path.lstat()),
         "FILE_CHANGED_OR_TOO_LARGE")
    return data


def trusted_parents(path):
    for part in path.parents:
        meta = part.lstat()
        need(stat.S_ISDIR(meta.st_mode) and meta.st_uid == meta.st_gid == 0,
             "PATH_PARENT_IDENTITY")
        if part == Path("/tmp"):
            need(meta.st_mode & stat.S_ISVTX, "TMP_PARENT_NOT_STICKY")
        else:
            need(not meta.st_mode & 0o022, "PATH_PARENT_WRITABLE")


def process(pid):
    row = read(PROC / str(pid) / "stat", 8192)
    head, marker, tail = row.rpartition(b") ")
    need(marker and head.startswith(f"{pid} (".encode()), "PROC_IDENTITY")
    fields = tail.split()
    return int(fields[19]), int(fields[1]), int(fields[2]), fields[0]


def cgroup(pid):
    root = PROC / str(pid)
    return read(root / "cgroup", 8192), os.readlink(root / "ns/cgroup")


def status(name):
    need(name in (*TARGETS, MODEL[0]), "SUPERVISOR_STATUS_OUT_OF_SCOPE")
    result = subprocess.run(["supervisorctl", "status", name], capture_output=True,
                            text=True, timeout=8, check=False)
    need(len(result.stdout) + len(result.stderr) <= 4096, "SUPERVISOR_STATUS_SIZE")
    combined = (result.stdout + result.stderr).strip()
    if result.returncode in (1, 3, 4) and re.fullmatch(
            rf"{re.escape(name)}\s+ERROR\s+\(no such process\)", combined):
        return {"statename": "NOT_REGISTERED"}
    parsed = re.fullmatch(
        rf"{re.escape(name)}\s+(RUNNING|STOPPED|STARTING|STOPPING|EXITED|FATAL|BACKOFF|UNKNOWN)"
        rf"(?:\s+([^\r\n]*))?", result.stdout.strip())
    need(parsed is not None, "SUPERVISOR_STATUS_FORMAT")
    state, details = parsed.groups()
    need(not result.stderr.strip() and result.returncode in (0, 3), "SUPERVISOR_STATUS_EXIT")
    if state != "RUNNING":
        return {"statename": state}
    pid = re.fullmatch(r"pid ([1-9][0-9]{0,9}), uptime [0-9:]+(?: day[s]?, [0-9:]+)?",
                       details or "")
    need(result.returncode == 0 and pid is not None, "SUPERVISOR_RUNNING_STATUS")
    return {"statename": state, "pid": int(pid[1])}


def protect_model():
    supervisor_pid, supervisor_ticks = SUPERVISOR
    name, pid, ticks = MODEL
    parent = process(supervisor_pid)
    observed = process(pid)
    need(parent[:2] == (supervisor_ticks, 1)
         and parent[3] not in (b"Z", b"X")
         and cgroup(supervisor_pid) == cgroup("self"), "SUPERVISOR_PROCESS_GENERATION")
    need(status(name) == {"statename": "RUNNING", "pid": pid}
         and observed[:3] == (ticks, supervisor_pid, pid)
         and observed[3] not in (b"Z", b"X")
         and cgroup(pid) == cgroup("self"), "MODEL_GENERATION_CHANGED")


def memory():
    need(cgroup("self")[0] == b"0::/\n", "CGROUP_NAMESPACE")
    names = ("anon", "file", "shmem", "inactive_file")
    stats = dict(line.split() for line in read(CGROUP / "memory.stat", 8192).decode().splitlines())
    return {"current": int(read(CGROUP / "memory.current", 128)),
            "limit": int(read(CGROUP / "memory.max", 128)),
            **{name: int(stats[name]) for name in names}}
