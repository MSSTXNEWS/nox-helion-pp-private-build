#!/usr/bin/env python3
"""One owner request to reclaim cold file cache in the original NOX container."""

import errno
from contextlib import ExitStack
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import stat
import time

GIB = 1024 ** 3
ROOT = Path("/root/nox")
CGROUP = Path("/sys/fs/cgroup")
EXPECTED_LIMIT = 194065203200
EXPECTED_BOOT = "9c0ecc02-85c1-452b-b8ae-521e9a11fd03"
MODEL = (3266857, 172046662)
KEEPER = (498569, 168416044)
MEMFD = (1, 131095, 75_266_239_716)
TARGET_HEADROOM = 8 * GIB
MIN_RECLAIMABLE = 8 * GIB
CHUNK = 512 * 1024 ** 2
MAX_CHUNKS = 6
MARKERS = (
    ROOT / "STOP", ROOT / "STOP.flag", ROOT / "stop.flag", ROOT / ".stop",
    ROOT / "program/STOP", ROOT / "state/STOP", ROOT / "state/STOP.flag",
    ROOT / "state/OWNER_MAINTENANCE.flag", Path("/workspace/NOX_STOP"),
)


class Hold(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def proc_start(pid):
    fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(") ", 1)[1].split()
    require(fields[0] not in ("Z", "X"), "MODEL_PROCESS_ABSENT")
    return int(fields[19])


def model_healthy():
    connection = http.client.HTTPConnection("127.0.0.1", 8098, timeout=3)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        return response.status == 200 and json.loads(response.read(4096)).get("status") == "ok"
    finally:
        connection.close()


def owner_scope():
    require(not any(os.path.lexists(path) for path in MARKERS), "OWNER_STOP_OR_MAINTENANCE")
    require(proc_start(MODEL[0]) == MODEL[1] and proc_start(KEEPER[0]) == KEEPER[1],
            "MODEL_OR_KEEPER_CHANGED")
    model_dir = Path("/proc") / str(MODEL[0])
    keeper_dir = Path("/proc") / str(KEEPER[0])
    for proc in (Path("/proc/self"), model_dir, keeper_dir):
        require((proc / "cgroup").read_text().strip() == "0::/", "CGROUP_NOT_SCOPED_ROOT")
    members = {int(pid) for pid in (CGROUP / "cgroup.procs").read_text().split()}
    require({os.getpid(), MODEL[0], KEEPER[0]} <= members, "CGROUP_MEMBERS_UNVERIFIED")
    fd_found = False
    for entry in (keeper_dir / "fd").iterdir():
        try:
            info = entry.stat()
        except FileNotFoundError:
            continue
        if (info.st_dev, info.st_ino, info.st_size) == MEMFD:
            fd_found = True
            break
    require(fd_found, "KEEPER_MEMFD_CHANGED")
    mapped = False
    for line in (model_dir / "maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        path = fields[5].lower()
        require(".gguf" not in path or path.startswith("/memfd:"),
                "FILE_BACKED_MODEL_NOT_EXCLUDED")
        if path.startswith("/memfd:") and int(fields[4]) == MEMFD[1]:
            major, minor = (int(item, 16) for item in fields[3].split(":"))
            mapped = mapped or os.makedev(major, minor) == MEMFD[0]
    require(mapped, "MODEL_MEMFD_NOT_MAPPED")
    require(model_healthy(), "MODEL_HEALTH")


def snapshot():
    def numbers(name):
        return {key: int(value) for key, value in
                (line.split() for line in (CGROUP / name).read_text().splitlines())}

    current = int((CGROUP / "memory.current").read_text())
    limit = int((CGROUP / "memory.max").read_text())
    require(limit == EXPECTED_LIMIT and current > 0, "CGROUP_LIMIT_CHANGED")
    stats = numbers("memory.stat")
    events = numbers("memory.events")
    psi = {}
    for line in (CGROUP / "memory.pressure").read_text().splitlines():
        category, first, *_ = line.split()
        require(first.startswith("avg10="), "MEMORY_PRESSURE_FORMAT")
        psi[category] = float(first.partition("=")[2])
    require(0 <= psi["full"] < 1 and 0 <= psi["some"] < 2, "MEMORY_PRESSURE")
    return {
        "current_bytes": current,
        "headroom_bytes": limit - current,
        "inactive_file_bytes": stats["inactive_file"],
        "shmem_bytes": stats["shmem"],
        "swap_bytes": int((CGROUP / "memory.swap.current").read_text()),
        "oom": events["oom"],
        "oom_kill": events["oom_kill"],
        "psi_avg10": psi,
    }


def write_reclaim(size):
    control = CGROUP / "memory.reclaim"
    # A v2 control must already exist on the exact scoped cgroup. Never retry
    # with the kernel default swappiness when this control rejects the option.
    payload = f"{size} swappiness=0".encode("ascii")
    fd = os.open(control, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "RECLAIM_CONTROL_TYPE")
        require(os.write(fd, payload) == len(payload), "SHORT_RECLAIM_WRITE")
        return "ACCEPTED"
    except OSError as error:
        if error.errno == errno.EAGAIN:
            return "PARTIAL"
        raise
    finally:
        os.close(fd)


def guarded_reclaim(report, *, capture=snapshot, write=write_reclaim, guard=owner_scope,
                    wait=time.sleep):
    guard()
    baseline = capture()
    report.update(before=baseline, samples=[], after=baseline, requested_bytes=0)
    current = baseline
    for _ in range(MAX_CHUNKS):
        if current["headroom_bytes"] >= TARGET_HEADROOM:
            break
        require(current["inactive_file_bytes"] >= MIN_RECLAIMABLE, "COLD_CACHE_TOO_SMALL")
        guard()
        size = min(CHUNK, TARGET_HEADROOM - current["headroom_bytes"])
        result = write(size)
        report["requested_bytes"] += size
        wait(1)
        updated = capture()
        report["samples"].append({"write": result, **updated})
        report["after"] = updated
        guard()
        require(updated["oom"] == baseline["oom"] and
                updated["oom_kill"] == baseline["oom_kill"], "OOM_EVENT_CHANGED")
        require(updated["swap_bytes"] <= baseline["swap_bytes"], "SWAP_INCREASED")
        require(updated["shmem_bytes"] >= baseline["shmem_bytes"] - 64 * 1024 ** 2,
                "PROTECTED_SHMEM_CHANGED")
        if updated["headroom_bytes"] <= current["headroom_bytes"]:
            break
        current = updated
    final = report["after"]
    gain = max(0, final["headroom_bytes"] - baseline["headroom_bytes"])
    cold_delta = max(0, baseline["inactive_file_bytes"] - final["inactive_file_bytes"])
    report["headroom_gain_bytes"] = gain
    report["inactive_file_reduction_bytes"] = cold_delta
    if report["requested_bytes"] and gain > 0 and cold_delta > 0:
        report["state"] = "RECLAIM_OBSERVED"
    elif report["requested_bytes"]:
        report["state"] = "RECLAIM_GAIN_NOT_OBSERVED"
    else:
        report["state"] = "NO_RECLAIM_ABOVE_FLOOR"


def main():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    report = {"schema": "NOX_OWNER_CGROUP_RECLAIM_V1", "request": request, "source": source}
    try:
        require(os.geteuid() == 0 and re.fullmatch("[0-9]{1,20}", request)
                and re.fullmatch("[0-9a-f]{40}", source), "OWNER_CONTEXT")
        require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == EXPECTED_BOOT,
                "HOST_BOOT_CHANGED")
        require(any(" /sys/fs/cgroup " in line and " - cgroup2 " in line
                    for line in Path("/proc/self/mountinfo").read_text().splitlines()),
                "NO_CGROUP_V2_MOUNT")
        with ExitStack() as locks:
            for lock, kind in (
                (ROOT / "state/owner_storage/reclaim.lock", fcntl.LOCK_EX),
                (ROOT / "state/owner_maintenance.lock", fcntl.LOCK_SH),
            ):
                fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                locks.callback(os.close, fd)
                lock_stat = os.fstat(fd)
                require(stat.S_ISREG(lock_stat.st_mode) and lock_stat.st_uid == 0 and
                        lock_stat.st_nlink == 1 and lock_stat.st_mode & 0o022 == 0, "LOCK_OWNERSHIP")
                fcntl.flock(fd, kind | fcntl.LOCK_NB)
            guarded_reclaim(report)
    except Hold as error:
        report["state"] = "HOLD_" + str(error)
    except OSError as error:
        report["state"] = "HOLD_" + errno.errorcode.get(error.errno, "OSERROR")
    except (ValueError, KeyError, IndexError, http.client.HTTPException) as error:
        report["state"] = "HOLD_" + type(error).__name__.upper()
    print("NOX_MAINT_CGROUP_RECLAIM=" + json.dumps(report, separators=(",", ":")), flush=True)
    if report["state"] in {"RECLAIM_OBSERVED", "NO_RECLAIM_ABOVE_FLOOR"}:
        print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
