#!/usr/bin/env python3
"""Summarize memory for the observed NOX Supervisor services without executing a controller."""

import configparser
import hashlib
import json
import os
from pathlib import Path
import stat
import time


PROC = Path("/proc")
SUPERVISOR = 114, 167791115
CONF = Path("/etc/supervisor/conf.d")
STATE = Path("/root/nox/state/dispatcher/state.json")
SERVICES = {
    "nox-cache-watchdog-t166u": (3352980, 172255925),
    "nox-chat-watchdog-t180u": (3367869, 172388718),
    "nox-dialog-miner": (3355768, 172313519),
    "nox-dispatcher-t855u": (359172, 184639742),
    "nox-ds41-8098": (3266857, 172046662),
    "nox-embed": (3353067, 172255944),
    "nox-fill-idle-t166u": (3352981, 172255926),
    "nox-gpu-idle-t170u": (3355350, 172305444),
    "nox-kb-eventlistener": (3355802, 172313892),
    "nox-knowledge-index-t168u": (3355682, 172312297),
    "nox-lifeline-guard": (3355691, 172312630),
    "nox-monitor-t131u": (2922729, 171594906),
    "nox-priority-arbiter": (3350646, 172209888),
    "nox-proxy": (356544, 184602380),
    "nox-selfheal": (3355733, 172313146),
    "nox-web29-18775": (356735, 184603716),
}
MEMORY_FIELDS = (
    "Rss", "Pss", "Pss_Anon", "Pss_File", "Pss_Shmem", "Private_Clean", "Private_Dirty"
)
BOOT_ID = "9c0ecc02-85c1-452b-b8ae-521e9a11fd03"
CONTROLLERS = tuple(map(Path, (
    "/usr/bin/supervisorctl", "/usr/local/bin/supervisorctl", "/opt/venv/bin/supervisorctl"
)))


def read_path(path, limit, verify_metadata=False):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not a regular file")
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
    if len(raw) > limit:
        raise ValueError("read exceeds fixed byte bound")
    if verify_metadata:
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or identity(before) != identity(os.lstat(path)):
            raise ValueError("file was replaced or changed")
    return raw, before


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_proc(pid, name, limit=8192):
    return read_path(PROC / str(pid) / name, limit)[0]


def identity(pid):
    raw = read_proc(pid, "stat")
    prefix, closing, suffix = raw.rpartition(b") ")
    if not closing or not prefix.startswith(f"{pid} (".encode()):
        raise ValueError("process stat identity missing")
    fields = suffix.split()
    if len(fields) < 20:
        raise ValueError("process stat truncated")
    return int(fields[19]), int(fields[1]), int(fields[2]), fields[0] == b"Z"


def service_binding(pid, service):
    environment = read_proc(pid, "environ", 256 * 1024)
    values = [item.split(b"=", 1)[1] for item in environment.split(b"\0")
              if item.startswith(b"SUPERVISOR_PROCESS_NAME=")]
    return values == [service.encode()] and b"SUPERVISOR_ENABLED=1" in environment.split(b"\0")


def rollup(pid):
    values = {}
    for line in read_proc(pid, "smaps_rollup", 16384).decode("ascii").splitlines():
        key, _, counter = line.partition(":")
        if key in MEMORY_FIELDS:
            amount, unit = counter.split()
            if key in values or not amount.isdecimal() or unit != "kB":
                raise ValueError("invalid process memory counter")
            values[key] = int(amount) * 1024
    if not {"Rss", "Pss", "Private_Clean", "Private_Dirty"} <= values.keys():
        raise ValueError("PSS or USS inputs missing")
    values["Uss"] = values["Private_Clean"] + values["Private_Dirty"]
    return values


def process_table():
    table = {}
    disappeared = 0
    try:
        with os.scandir(PROC) as entries:
            candidates = []
            for entry in entries:
                if entry.name.isascii() and entry.name.isdecimal():
                    candidates.append(int(entry.name))
                    if len(candidates) > 512:
                        return table, False
    except OSError:
        return table, False
    for pid in candidates:
        try:
            table[pid] = identity(pid)
        except (OSError, ValueError):
            disappeared += 1
    return table, disappeared == 0


def descendants(table, root):
    descendants = {root}
    for _ in range(len(table)):
        extended = descendants | {pid for pid, row in table.items() if row[1] in descendants}
        if descendants == extended:
            break
        descendants = extended
    return sorted(descendants - {root})


def config_rows():
    rows = {name: [] for name in SERVICES}
    candidates = sorted(CONF.glob("*.conf"))
    if len(candidates) > 96:
        raise ValueError("Supervisor include file limit exceeded")
    errors = 0
    for path in candidates:
        try:
            raw, stamp = read_path(path, 256 * 1024, verify_metadata=True)
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.read_string(raw.decode("utf-8"))
            for service, matches in rows.items():
                section = "program:" + service
                if not parser.has_section(section):
                    continue
                program = parser[section]
                stop_signal = program.get("stopsignal", "TERM").upper()
                autorestart = program.get("autorestart", "unexpected").lower()
                matches.append({
                    "include_basename": path.name,
                    "sha256": digest(raw),
                    "uid": stamp.st_uid,
                    "gid": stamp.st_gid,
                    "mode": oct(stat.S_IMODE(stamp.st_mode)),
                    "command_sha256": digest(program.get("command", "").encode()),
                    "stopasgroup": program.getboolean("stopasgroup", fallback=False),
                    "killasgroup": program.getboolean("killasgroup", fallback=False),
                    "stopsignal": stop_signal if stop_signal in ("TERM", "INT", "QUIT", "KILL", "USR1", "USR2", "HUP") else "OTHER",
                    "stopwaitsecs": program.getint("stopwaitsecs", fallback=10),
                    "autorestart": autorestart if autorestart in ("true", "false", "unexpected") else "OTHER",
                })
        except (ValueError, UnicodeError, OSError, configparser.Error):
            errors += 1
    return rows, errors


def controllers():
    results = []
    for path in CONTROLLERS:
        item = {"path": str(path)}
        try:
            raw, stamp = read_path(path, 256 * 1024, verify_metadata=True)
            parent_metadata = [os.lstat(parent) for parent in path.parents]
            item.update({
                "state": "OBSERVED",
                "kind": "SCRIPT" if raw.startswith(b"#!") else "ELF" if raw.startswith(b"\x7fELF") else "OTHER",
                "uid": stamp.st_uid,
                "gid": stamp.st_gid,
                "mode": oct(stat.S_IMODE(stamp.st_mode)),
                "sha256": digest(raw),
                "root_only_write_metadata": stamp.st_uid == 0 and not stamp.st_mode & 0o022
                and all(meta.st_uid == 0 and stat.S_ISDIR(meta.st_mode) and not meta.st_mode & 0o022
                        for meta in parent_metadata),
                "execution_trusted": False,
            })
        except FileNotFoundError:
            item["state"] = "ABSENT"
        except (OSError, ValueError):
            item["state"] = "UNREADABLE_OR_UNSTABLE"
        results.append(item)
    return results


def queue_summary():
    raw = read_path(STATE, 16 * 1024 * 1024, verify_metadata=True)[0]
    tasks = json.loads(raw)["tasks"]
    if type(tasks) is not dict:
        raise ValueError("unknown queue schema")
    terminal = {"done", "completed", "failed", "blocked", "cancelled"}
    active = unsettled = unknown = 0
    for item in tasks.values():
        if type(item) is not dict or not isinstance(item.get("status"), str):
            unknown += 1
            continue
        if item["status"] in terminal:
            continue
        active += int(item["status"] in ("running", "admitted", "retry")
                      or any(item.get(key) for key in ("claim", "owner_claim", "native_pool_recovery")))
        lease = item.get("native_worker_lease")
        unsettled += int(lease is not None and
                         (not isinstance(lease, dict) or lease.get("phase") != "SETTLED"))
    return {"sha256": digest(raw), "active_or_claimed": active, "unsettled_leases": unsettled,
            "unclassified_rows": unknown, "total_rows": len(tasks)}


def group_path():
    path = Path("/sys/fs/cgroup")
    unified = [line[3:] for line in read_proc("self", "cgroup").decode().splitlines()
               if line.startswith("0::")]
    if unified != ["/"]:
        raise ValueError("expected the audited cgroup namespace root")
    matching_mounts = []
    for line in read_proc("self", "mountinfo", 128 * 1024).decode().splitlines():
        mount, separator, filesystem = line.partition(" - ")
        fields = mount.split()
        if separator and len(fields) >= 5 and fields[4] == str(path):
            matching_mounts.append((fields[3], filesystem.split()[0]))
    if matching_mounts != [("/", "cgroup2")]:
        raise ValueError("cgroup2 mount is not the expected namespace root")
    return path


def cgroup_identity(pid):
    path = PROC / str(pid)
    return read_proc(pid, "cgroup"), os.readlink(path / "ns/cgroup")


def memory_group(root):
    current = int(read_path(root / "memory.current", 128)[0])
    maximum = int(read_path(root / "memory.max", 128)[0])
    counts = {}
    for name in ("memory.stat", "memory.events"):
        lines = read_path(root / name, 8192)[0].decode().splitlines()
        counts[name] = {key: int(value) for key, value in map(str.split, lines)}
    return {
        "current_bytes": current, "max_bytes": maximum, "headroom_bytes": maximum - current,
        "events": counts["memory.events"],
        "stats": {key: counts["memory.stat"].get(key)
                  for key in ("anon", "shmem", "file", "inactive_file", "file_mapped", "kernel")},
        "pressure": read_path(root / "memory.pressure", 2048)[0].decode().splitlines(),
    }


def collect():
    begin = time.time()
    if read_path(PROC / "sys/kernel/random/boot_id", 128)[0].decode().strip() != BOOT_ID:
        raise ValueError("boot epoch differs from parent audit")
    if identity(SUPERVISOR[0])[:2] != (SUPERVISOR[1], 1):
        raise ValueError("Supervisor identity differs from parent audit")
    root = group_path()
    before = memory_group(root)
    self_cgroup = cgroup_identity("self")
    configs, config_errors = config_rows()
    processes, first_complete = process_table()
    queue_before = queue_summary()
    sized = {}
    for service, (pid, ticks) in SERVICES.items():
        expected = processes.get(pid)
        record = {"pid": pid, "expected_start_ticks": ticks, "config": configs[service]}
        try:
            if (expected is None or expected[:2] != (ticks, SUPERVISOR[0])
                    or expected[3] or not service_binding(pid, service)
                    or cgroup_identity(pid) != self_cgroup):
                raise ValueError("audited service, process or cgroup binding changed")
            children = descendants(processes, pid)
            measurements = {}
            for member in (pid, *children):
                if (identity(member) != processes[member] or
                        cgroup_identity(member) != self_cgroup):
                    raise ValueError("group member identity changed")
                row = rollup(member)
                if identity(member) != processes[member]:
                    raise ValueError("group member changed during sample")
                measurements[member] = row
            record.update({"state": "SAMPLED", "children": children, "self_bytes": measurements[pid],
                           "total_pss_bytes": sum(row["Pss"] for row in measurements.values()),
                           "total_uss_bytes": sum(row["Uss"] for row in measurements.values())})
        except (OSError, ValueError):
            record["state"] = "UNVERIFIED_OR_UNREADABLE"
        sized[service] = record
    final_processes, last_complete = process_table()
    for record in sized.values():
        pid = record["pid"]
        if (record["state"] == "SAMPLED"
                and (descendants(final_processes, pid) != record["children"]
                     or any(final_processes.get(member) != processes.get(member)
                            for member in (pid, *record["children"])))):
            record["state"] = "STALE_SAMPLE_PROCESS_SET_CHANGED"
    queue_after = queue_summary()
    after = memory_group(root)
    complete = first_complete and last_complete and config_errors == 0 and all(
        record["state"] == "SAMPLED" and len(record["config"]) == 1 for record in sized.values()
    )
    return {
        "schema": "NOX_READ_ONLY_SERVICE_MEMORY_EVIDENCE_V1",
        "state": "SAMPLED_COMPLETE" if complete else "SAMPLED_PARTIAL",
        "start_unix": begin,
        "end_unix": time.time(),
        "owner_request": os.environ.get("NOX_OWNER_REQUEST_ID"),
        "source_sha": os.environ.get("NOX_OWNER_SOURCE_SHA"),
        "host_mutations": False,
        "signals_sent": False,
        "stop_admission": False,
        "supervisor_pid": SUPERVISOR[0],
        "supervisor_start_ticks": SUPERVISOR[1],
        "process_census_complete": first_complete and last_complete,
        "config_parse_errors": config_errors,
        "cgroup_before": before,
        "cgroup_after": after,
        "queue_before": queue_before,
        "queue_after": queue_after,
        "controller_observation": controllers(),
        "services": sized,
    }


if __name__ == "__main__":
    try:
        result = collect()
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        result = {"schema": "NOX_READ_ONLY_SERVICE_MEMORY_EVIDENCE_V1", "state": "HOLD",
                  "error_class": type(exc).__name__, "host_mutations": False, "signals_sent": False}
    delivered_samples = sum(
        record["state"] == "SAMPLED" for record in result.get("services", {}).values()
    )
    result["stable_samples"] = delivered_samples
    result["scope_complete"] = result["state"] == "SAMPLED_COMPLETE"
    print("NOX_MAINT_SERVICE_MEMORY_EVIDENCE=" + json.dumps(result, separators=(",", ":")))
    if delivered_samples:
        print("NOX_MAINT_REPAIR_COMPLETE=true")
    raise SystemExit(0 if delivered_samples else 2)
