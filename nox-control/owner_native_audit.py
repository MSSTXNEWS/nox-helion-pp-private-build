#!/usr/bin/env python3
"""One-shot native audit. Seven bounded OS workers, no daemon, no mutation or credentials output."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, time, stat
import datetime as dt

SAFE=re.compile(r'^[A-Za-z0-9_./+@:= -]{1,300}$')
ROOTS=('/root/nox','/root/nox_learn','/workspace')

def run(argv, seconds=12):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=seconds)
        return p.returncode,p.stdout[:200000]
    except Exception as e:return 99,type(e).__name__

def num(path):
    try:
        v=Path(path).read_text().strip()
        return int(v) if v.isdigit() else v[:40]
    except OSError:return None

def hardware():
    rc,g=run(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
    _,a=run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
    return {'gpu_rc':rc,'gpu':[x for x in g.splitlines() if SAFE.fullmatch(x.replace(',',''))][:4],
      'gpu_apps':[x for x in a.splitlines() if SAFE.fullmatch(x.replace(',',''))][:16],
      'gpu_pid_evidence':gpu_pid_evidence(a),
      'cpus':os.cpu_count(),'load':list(os.getloadavg()),
      'cgroup_max':num('/sys/fs/cgroup/memory.max'),'cgroup_current':num('/sys/fs/cgroup/memory.current'),
      'cpu_max':num('/sys/fs/cgroup/cpu.max'),
      'disk':{r:dict(zip(('total','used','free'),shutil.disk_usage(r))) for r in ROOTS if Path(r).is_dir()}}

def proc_start_ticks(proc_dir, expected_pid):
    """Read Linux /proc/<pid>/stat field 22; verify PID despite ')' in comm.

    A numeric PID without a validated start tick is not proof of process identity.
    Do not export cmdline, environment, or the raw stat record.
    """
    raw=(Path(proc_dir)/'stat').read_text()
    prefix=str(expected_pid)+' ('
    boundary=raw.rfind(') ')
    if not raw.startswith(prefix) or boundary<len(prefix):
        raise ValueError('HOLD_PID_STAT_IDENTITY')
    fields=raw[boundary+2:].split()
    if len(fields)<20 or not fields[19].isdigit():
        raise ValueError('HOLD_PID_START_TICKS')
    return int(fields[19])

def process_rows(proc_root=Path('/proc')):
    rows=[]
    flags={'-m','--model','--model-path','--model_path','--base-model','--student','--output_dir','--output-dir','--config','-c'}
    for p in Path(proc_root).iterdir():
        if not p.name.isdigit():continue
        try:
            initial_ticks=proc_start_ticks(p,int(p.name))
            argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not any(k in ' '.join(argv[:3]).lower() for k in ('nox','llama','train','python','supervisor','rclone','jupyter')):continue
            args=[]
            for i,v in enumerate(argv):
                if v in flags and i+1<len(argv) and SAFE.fullmatch(argv[i+1]) and '://' not in argv[i+1]:args.append([v,argv[i+1]])
            row={'pid':int(p.name),'comm':(p/'comm').read_text().strip()[:60],
                 'executable':os.path.basename(argv[0]),'arguments':args[:12]}
            scripts=[v for v in argv[1:5] if v.endswith(('.py','.sh')) and SAFE.fullmatch(v)]
            if scripts:row['scripts']=scripts
            # Do not attribute a reused PID to the model observed earlier.
            if proc_start_ticks(p,int(p.name)) != initial_ticks:continue
            row['start_ticks']=initial_ticks
            rows.append(row)
        except (OSError,ValueError):continue
    return rows[:100]


# Fixed prior owner audit candidate: reuse this PID only if the kernel start tick
# still matches. A PID reuse is reported as a mismatch and never inspected.
EXACT_PID_CANDIDATES = (
    (498569, 168416044, "EXACT_PRIOR_MEMFD_CANDIDATE"),
    (3266857, 172046662, "OWNER_CONFIRMED_SERVING_PEER"),
)
PROC_EVIDENCE_LIMITS = {
    "fd_entries": 256, "maps_bytes": 1048576, "maps_lines": 8192,
    "memfd_maps": 8, "fd_rows": 8, "smaps_rollup_bytes": 8192,
    "total_processes": 18, "total_json_bytes": 88000,
}
MEMFD_LABEL = re.compile(r"^/?memfd:([A-Za-z0-9_.+@=-]{1,96}) \(deleted\)$")
NVIDIA_FD = re.compile(r"^/dev/(?:nvidiactl|nvidia-uvm(?:-tools)?|nvidia[0-9]+)$")
CGROUP_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
SMAPS_KEYS = {"Rss", "Pss", "Shared_Clean", "Shared_Dirty", "Private_Clean",
              "Private_Dirty", "Anonymous", "Swap"}

def _read_bounded(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False

def _memfd_label(target):
    m = MEMFD_LABEL.fullmatch(target)
    return m[1] if m else None

def _safe_cgroup(pid_path):
    """Read only unified cgroup path and allowlisted memory counters."""
    try:
        raw, truncated = _read_bounded(pid_path / "cgroup", 8192)
        if truncated:
            return {"status": "CGROUP_RECORD_TRUNCATED"}
        lines = raw.decode("ascii", errors="strict").splitlines()
        rows = [line for line in lines if line.startswith("0::")]
        if len(rows) != 1:
            return {"status": "CGROUP_V2_NOT_UNIQUE"}
        rel = rows[0][3:]
        parts = rel.strip("/").split("/") if rel.strip("/") else []
        if any(part in (".", "..") or not CGROUP_COMPONENT.fullmatch(part)
               for part in parts):
            return {"status": "CGROUP_PATH_NOT_ALLOWLISTED"}
        root = Path("/sys/fs/cgroup")
        base = root.joinpath(*parts)
        try:
            if os.path.commonpath((str(root.resolve()), str(base.resolve()))) != str(root.resolve()):
                return {"status": "CGROUP_PATH_ESCAPES_ROOT"}
        except OSError:
            return {"status": "CGROUP_PATH_UNAVAILABLE"}
        result = {"status": "CGROUP_V2", "path": "/" + "/".join(parts)}
        for name in ("memory.current", "memory.max"):
            try:
                value, cut = _read_bounded(base / name, 128)
                text = value.decode("ascii").strip()
                if cut or not (text == "max" or text.isdecimal()):
                    result[name] = "UNKNOWN"
                else:
                    result[name] = text if text == "max" else int(text)
            except OSError:
                result[name] = "UNAVAILABLE"
        try:
            value, cut = _read_bounded(base / "memory.stat", 4096)
            stats = {}
            if not cut:
                for line in value.decode("ascii").splitlines():
                    fields = line.split()
                    if len(fields) == 2 and fields[0] in ("anon", "file", "shmem"):
                        if fields[1].isdecimal():
                            stats[fields[0]] = int(fields[1])
            result["memory.stat"] = stats
            result["memory.stat_truncated"] = cut
        except (OSError, UnicodeError):
            result["memory.stat"] = "UNAVAILABLE"
        return result
    except (OSError, UnicodeError):
        return {"status": "CGROUP_UNAVAILABLE"}

def _smaps_rollup(pid_path):
    try:
        raw, truncated = _read_bounded(pid_path / "smaps_rollup",
                                       PROC_EVIDENCE_LIMITS["smaps_rollup_bytes"])
        values = {}
        if not truncated:
            for line in raw.decode("ascii", errors="strict").splitlines():
                fields = line.split()
                if len(fields) == 3 and fields[0].rstrip(":") in SMAPS_KEYS:
                    key = fields[0].rstrip(":")
                    if fields[1].isdecimal() and fields[2] == "kB":
                        values[key + "_kB"] = int(fields[1])
        return {"values": values, "truncated": truncated}
    except (OSError, UnicodeError):
        return {"status": "SMAPS_ROLLUP_UNAVAILABLE"}

def _fd_evidence(pid_path):
    """Export only allowlisted memfd labels or NVIDIA device paths, plus stat."""
    rows = []
    scanned = 0
    truncated = False
    entries = []
    try:
        with os.scandir(pid_path / "fd") as directory:
            for entry in directory:
                if len(entries) >= PROC_EVIDENCE_LIMITS["fd_entries"]:
                    truncated = True
                    break
                if entry.name.isdecimal():
                    entries.append(Path(entry.path))
        entries.sort(key=lambda p: int(p.name))
    except OSError:
        return {"status": "FD_DIRECTORY_UNAVAILABLE", "rows": [], "scanned": 0}
    for fd in entries:
        scanned += 1
        try:
            target = os.readlink(fd)
            memfd = _memfd_label(target)
            if memfd is not None:
                target_kind = "DELETED_MEMFD"
                safe_target = "memfd:" + memfd + " (deleted)"
            elif NVIDIA_FD.fullmatch(target):
                target_kind = "NVIDIA_DEVICE"
                safe_target = target
            else:
                continue
            info = os.stat(fd)
            row = {"fd": int(fd.name), "target_kind": target_kind,
                   "target": safe_target, "device": int(info.st_dev),
                   "inode": int(info.st_ino), "size_bytes": int(info.st_size),
                   "mode": stat.S_IFMT(info.st_mode)}
            if memfd is not None and not stat.S_ISREG(info.st_mode):
                row["target_kind"] = "DELETED_MEMFD_NONREGULAR"
            rows.append(row)
        except (OSError, ValueError):
            continue
    return {"status": "OK", "rows": rows[:PROC_EVIDENCE_LIMITS["fd_rows"]], "scanned": scanned,
            "truncated": truncated or len(rows) > PROC_EVIDENCE_LIMITS["fd_rows"]}

def _deleted_memfd_maps(pid_path):
    """Bound /proc/PID/maps bytes and export parsed deleted-memfd rows only."""
    rows = []
    seen_lines = 0
    total_bytes = 0
    truncated = False
    try:
        with (pid_path / "maps").open("rb") as stream:
            while seen_lines < PROC_EVIDENCE_LIMITS["maps_lines"]:
                raw = stream.readline(4096)
                if not raw:
                    break
                total_bytes += len(raw)
                if total_bytes > PROC_EVIDENCE_LIMITS["maps_bytes"]:
                    truncated = True
                    break
                seen_lines += 1
                try:
                    fields = raw.decode("utf-8", errors="replace").rstrip("\n").split(None, 5)
                    if len(fields) != 6:
                        continue
                    address, perms, offset, device, inode_text, label = fields
                    name = _memfd_label(label)
                    if name is None or not inode_text.isdecimal():
                        continue
                    start_text, end_text = address.split("-", 1)
                    start, end = int(start_text, 16), int(end_text, 16)
                    if end <= start or not re.fullmatch(r"[0-9a-fA-F]+", offset):
                        continue
                    rows.append({"start": start, "end": end, "size_bytes": end - start,
                                 "permissions": perms[:4], "offset": int(offset, 16),
                                 "device": device[:16], "inode": int(inode_text),
                                 "memfd": name + " (deleted)"})
                    if len(rows) >= PROC_EVIDENCE_LIMITS["memfd_maps"]:
                        truncated = True
                        break
                except (ValueError, UnicodeError):
                    continue
            else:
                truncated = True
    except OSError:
        return {"status": "MAPS_UNAVAILABLE", "rows": [], "scanned_lines": seen_lines}
    return {"status": "OK", "rows": rows, "scanned_lines": seen_lines,
            "scanned_bytes": total_bytes, "truncated": truncated}

def _proc_stat_identity(pid_path, expected_pid):
    path = Path(pid_path) / "stat"
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        raw_bytes = os.read(fd, 8193)
    finally:
        os.close(fd)
    if len(raw_bytes) > 8192:
        raise ValueError("PROC_STAT_OVER_LIMIT")
    raw = raw_bytes.decode("ascii", errors="strict")
    prefix = str(expected_pid) + " ("
    boundary = raw.rfind(") ")
    if not raw.startswith(prefix) or boundary < len(prefix):
        raise ValueError("PROC_STAT_PID_MISMATCH")
    fields = raw[boundary + 2:].split()
    if len(fields) < 20 or not fields[19].isdecimal() or not fields[1].isdecimal() or not fields[2].isdecimal():
        raise ValueError("PROC_STAT_FIELDS_INVALID")
    return {"state": fields[0], "ppid": int(fields[1]), "pgrp": int(fields[2]),
            "start_ticks": int(fields[19])}

def process_pid_evidence(pid, expected_start_ticks=None, label="GPU_APP"):
    """Read-only, bounded process metadata. Never read target-file contents or signal."""
    if type(pid) is not int or pid <= 0:
        return {"pid": pid, "status": "INVALID_PID", "label": label}
    p = Path("/proc") / str(pid)
    try:
        first_stat = _proc_stat_identity(p, pid)
        first_ticks = first_stat["start_ticks"]
    except (OSError, ValueError):
        return {"pid": pid, "label": label, "status": "NOT_VISIBLE_OR_UNREADABLE"}
    base = {"pid": pid, "label": label, "stat": first_stat,
            "start_ticks": first_ticks, "expected_start_ticks": expected_start_ticks}
    if expected_start_ticks is not None and first_ticks != expected_start_ticks:
        return {"pid": pid, "label": label, "status": "PID_REUSE_OR_EXPECTED_START_TICK_MISMATCH",
                "observed_start_ticks": first_ticks, "expected_start_ticks": expected_start_ticks}
    try:
        status_raw, cut = _read_bounded(p / "status", 65536)
        nspid = []
        if not cut:
            for line in status_raw.decode("ascii", errors="replace").splitlines():
                if line.startswith("NSpid:"):
                    nspid = [int(v) for v in line.split()[1:4] if v.isdecimal()]
                    break
        result = {**base, "status": "READ_ONLY_SNAPSHOT",
                  "namespace_pids": nspid, "status_truncated": cut,
                  "cgroup": _safe_cgroup(p), "smaps_rollup": _smaps_rollup(p),
                  "fds": _fd_evidence(p), "deleted_memfd_maps": _deleted_memfd_maps(p)}
        last_stat = _proc_stat_identity(p, pid)
        last_ticks = last_stat["start_ticks"]
        if last_ticks != first_ticks:
            return {"pid": pid, "label": label, "status": "PID_CHANGED_DURING_READ",
                    "start_ticks_before": first_ticks, "start_ticks_after": last_ticks}
        result["identity_stable_during_read"] = True
        return result
    except (OSError, ValueError, UnicodeError):
        return {**base, "status": "PARTIAL_OR_UNREADABLE"}

def gpu_pid_evidence(gpu_app_output):
    """Prioritize exact owner-confirmed candidates, then bounded GPU-app PIDs."""
    rows = []
    seen = set()
    for pid, ticks, label in EXACT_PID_CANDIDATES:
        rows.append(process_pid_evidence(pid, ticks, label=label))
        seen.add(pid)
    truncated = False
    for line in gpu_app_output.splitlines()[:16]:
        fields = [part.strip() for part in line.split(",")]
        if not fields or not fields[0].isdecimal():
            continue
        pid = int(fields[0])
        if pid in seen:
            continue
        row = process_pid_evidence(pid, label="NVIDIA_SMI_GPU_APP")
        candidate = {"schema": "NOX_GPU_PID_PROCESS_EVIDENCE_V1",
                     "read_only": True, "file_contents_read": False,
                     "signals_sent": 0, "process_limit": PROC_EVIDENCE_LIMITS["total_processes"],
                     "processes": rows + [row]}
        size = len(json.dumps(candidate, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
        if size > PROC_EVIDENCE_LIMITS["total_json_bytes"]:
            truncated = True
            break
        rows.append(row)
        seen.add(pid)
    result = {"schema": "NOX_GPU_PID_PROCESS_EVIDENCE_V1",
              "read_only": True, "file_contents_read": False,
              "signals_sent": 0, "process_limit": PROC_EVIDENCE_LIMITS["total_processes"],
              "processes": rows, "truncated": truncated}
    result["serialized_bytes"] = len(json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
    return result

def v13_owner_fence_metadata(root=Path('/root/nox'), workspace_stop=Path('/workspace/NOX_STOP'), lstat=os.lstat):
    """READ-ONLY marker presence, not authorization to start, stop, or write.

    Preserve unreadable markers as UNKNOWN; missing flags at one instant are
    never evidence of an owner lease, safe release, or completed shutdown.
    Do not open, follow, hash or export marker contents.
    """
    paths = {
        'STOP': root / 'STOP',
        'STOP_FLAG': root / 'STOP.flag',
        'LOWER_STOP_FLAG': root / 'stop.flag',
        'DOT_STOP': root / '.stop',
        'PROGRAM_STOP': root / 'program/STOP',
        'STATE_STOP': root / 'state/STOP',
        'STATE_STOP_FLAG': root / 'state/STOP.flag',
        'MEDIA_STOP': root / 'state/MEDIA_STOP.flag',
        'OWNER_MAINTENANCE': root / 'state/OWNER_MAINTENANCE.flag',
        'WORKSPACE_STOP': workspace_stop,
        'TRAIN_HOLD': root / 'state/TRAIN_HOLD.flag',
    }
    rows = {}
    for name, path in paths.items():
        try:
            lstat(path)
            rows[name] = 'PRESENT'
        except FileNotFoundError:
            rows[name] = 'NOT_FOUND_AT_SNAPSHOT'
        except OSError:
            rows[name] = 'UNKNOWN_UNREADABLE'
    owner_names = tuple(name for name in rows if name != 'TRAIN_HOLD')
    owner_observed = [rows[name] for name in owner_names]
    status = ('PRESENT' if 'PRESENT' in owner_observed else
              'UNKNOWN' if 'UNKNOWN_UNREADABLE' in owner_observed else
              'NOT_OBSERVED_NOT_AUTHORIZED')
    return {
        'scope': 'READ_ONLY_MARKER_METADATA',
        'owner_stop_state': status,
        'train_hold_state': rows['TRAIN_HOLD'],
        'markers': rows,
        'owner_lease_state': 'NOT_CHECKED',
        'may_clear_stop': False,
        'may_start_nox': False,
        'may_write_native': False,
        'pid_starttime_verified': False,
    }



LIFELINE_SERVICE = "nox-lifeline-guard"
LIFELINE_EXPECTED_ARGV = [
    "/usr/bin/python3", "-u", "/root/nox/scripts/nox_native_lifeline.py",
    "--policy", "/etc/nox/lifeline.json",
    "--state", "/root/nox/state/lifeline/state.json",
]
LIFELINE_EXPECTED_EXE = os.path.realpath("/usr/bin/python3")
LIFELINE_MEMORY_FLOOR = 2 * 1024 ** 3
LIFELINE_REPORT_MAX_AGE_SECONDS = 180
LIFELINE_PRE_SCRIPT_SHA256 = "a2503c1463738c215bf3cd4eb5cdcb29f5ff65a85128160728033a80e9af1f66"
LIFELINE_PRE_CONFIG_SHA256 = "266d75d12cb3203dd8200a6b382231105a0fd3fd9ea37379531d86c413ddfba6"
LIFELINE_EXPECTED_SCRIPT_SHA256 = "d10b12461cdf08a309ea7ac08c81a6d465d254f95b78b1d3b441e7f59f01e69f"
LIFELINE_POLICY_SHA256 = "e06d45654fd664f9d15a057fbb5290dd862c4087dba383764283dbaab51edc5b"
LIFELINE_RECONCILED_CONFIG_SHA256 = "a7f3da89d408f9c9b1f261b0b5c58d55d0a7a095e36a2a22d6e378370b9c6bdf"
LIFELINE_PRE_GUARD_PID = 3355691
LIFELINE_PRE_GUARD_START_TICKS = 172312630
LIFELINE_FILES = {
    "script": ("/root/nox/scripts/nox_native_lifeline.py", 32768),
    "policy": ("/etc/nox/lifeline.json", 32768),
    "supervisor_config": ("/etc/supervisor/conf.d/nox-lifeline-guard.conf", 8192),
    "state": ("/root/nox/state/lifeline/state.json", 1048576),
}
LIFELINE_SERVICES = {
    "nox-dispatcher-t855u", "nox-priority-scheduler",
    "nox-selfheal", "nox-gpu-watchdog-t865u",
}

def _lifeline_unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def _lifeline_reject_constant(value):
    raise ValueError("NONFINITE_JSON_VALUE")

def _lifeline_read_allowlisted_file(name):
    """Read one fixed file with no-follow, bounded regular-file semantics."""
    entry = LIFELINE_FILES.get(name)
    if entry is None:
        return {"file": name, "status": "NOT_ALLOWLISTED"}, None
    path_text, limit = entry
    path = Path(path_text)
    for parent in reversed(path.parents):
        if parent == Path("/"):
            continue
        try:
            if stat.S_ISLNK(parent.lstat().st_mode):
                return {"file": name, "path": path_text, "status": "UNSAFE_PARENT"}, None
        except OSError:
            return {"file": name, "path": path_text, "status": "UNREADABLE_PARENT"}, None
    if not hasattr(os, "O_NOFOLLOW"):
        return {"file": name, "path": path_text, "status": "NOFOLLOW_UNAVAILABLE"}, None
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path_text, flags)
    except FileNotFoundError:
        return {"file": name, "path": path_text, "status": "NOT_FOUND"}, None
    except OSError:
        return {"file": name, "path": path_text, "status": "OPEN_REFUSED_OR_UNREADABLE"}, None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return {"file": name, "path": path_text, "status": "NOT_REGULAR_OR_HARDLINKED"}, None
        metadata = {"file": name, "path": path_text,
                    "mode": format(stat.S_IMODE(before.st_mode), "04o"),
                    "uid": int(before.st_uid), "size_bytes": int(before.st_size)}
        if before.st_size > limit:
            return {**metadata, "status": "SIZE_LIMIT"}, None
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        signature_before = (before.st_dev, before.st_ino, before.st_size,
                            before.st_mtime_ns, before.st_ctime_ns)
        signature_after = (after.st_dev, after.st_ino, after.st_size,
                           after.st_mtime_ns, after.st_ctime_ns)
        if (len(raw) > limit or len(raw) != before.st_size or
                signature_before != signature_after):
            return {**metadata, "status": "CHANGED_OR_SIZE_LIMIT"}, None
        return {**metadata, "sha256": hashlib.sha256(raw).hexdigest(),
                "status": "READ_OK_METADATA_ONLY"}, raw
    except OSError:
        return {"file": name, "path": path_text, "status": "READ_FAILED"}, None
    finally:
        os.close(fd)

def _lifeline_policy_fields(raw):
    result = {"parse_status": "INVALID_OR_UNREADABLE", "enabled": None,
              "poll_seconds": None, "restart_flags": {}}
    if raw is None:
        return result
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_lifeline_unique_pairs,
                           parse_constant=_lifeline_reject_constant)
        if not isinstance(value, dict) or value.get("schema") != "NOX_LIFELINE_V2":
            result["parse_status"] = "SCHEMA_MISMATCH"
            return result
        enabled = value.get("enabled")
        poll = value.get("poll_seconds")
        if type(enabled) is not bool or type(poll) is not int or not 15 <= poll <= 600:
            result["parse_status"] = "POLICY_FIELDS_INVALID"
            return result
        flags = {}
        services = value.get("services")
        if not isinstance(services, list) or not 1 <= len(services) <= len(LIFELINE_SERVICES):
            result["parse_status"] = "POLICY_SERVICES_INVALID"
            return result
        seen = set()
        for item in services:
            if (not isinstance(item, dict) or set(item) != {"name", "restart"}
                    or item.get("name") not in LIFELINE_SERVICES
                    or item.get("name") in seen or type(item.get("restart")) is not bool):
                result["parse_status"] = "POLICY_SERVICE_FIELDS_INVALID"
                return result
            seen.add(item["name"])
            flags[item["name"]] = item["restart"]
        result.update({"parse_status": "POLICY_FIELDS_PARSED",
                       "enabled": enabled, "poll_seconds": poll,
                       "restart_flags": flags})
        return result
    except (ValueError, TypeError, UnicodeError):
        return result

def _lifeline_supervisor_service(binary, config):
    if not binary:
        return {"status": "SUPERVISORCTL_UNAVAILABLE"}
    argv = [binary] + (["-c", config] if config else []) + ["status", LIFELINE_SERVICE]
    rc, output = run(argv, seconds=12)
    lines = output.strip().splitlines()
    if rc not in (0, 3) or len(lines) != 1:
        return {"status": "SUPERVISOR_STATUS_UNKNOWN", "rc": rc}
    match = re.match(r"^([A-Za-z0-9_.:-]+)\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)\b(.*)$", lines[0])
    if not match or match[1] != LIFELINE_SERVICE:
        return {"status": "SUPERVISOR_ROW_NOT_EXACT", "rc": rc}
    state, tail = match[2], match[3]
    pid_tokens = re.findall(r"\bpid\s+([0-9]+)", tail)
    if re.search(r"\bpid\b", tail, re.IGNORECASE) and len(pid_tokens) != 1:
        return {"status": "SUPERVISOR_PID_MALFORMED", "rc": rc}
    if pid_tokens and (len(pid_tokens[0]) > 10 or int(pid_tokens[0]) <= 0):
        return {"status": "SUPERVISOR_PID_OUT_OF_RANGE", "rc": rc}
    pid = int(pid_tokens[0]) if pid_tokens else None
    if rc == 3 and state not in ("STOPPED", "EXITED"):
        return {"status": "SUPERVISOR_RC_STATE_CONFLICT", "rc": rc}
    if (state == "RUNNING" and not pid) or (state in ("STOPPED", "EXITED") and pid is not None):
        return {"status": "SUPERVISOR_PID_STATE_CONFLICT", "rc": rc}
    result = {"status": "EXACT_SERVICE_ROW", "service": LIFELINE_SERVICE,
              "state": state, "pid": pid, "rc": rc}
    if state != "RUNNING" or pid is None:
        return result
    proc = Path("/proc") / str(pid)
    try:
        before = _proc_stat_identity(proc, pid)
        cmdline, truncated = _read_bounded(proc / "cmdline", 8192)
        if truncated:
            return {**result, "status": "PROCESS_CMDLINE_TRUNCATED",
                    "start_ticks": before["start_ticks"]}
        raw_argv = [arg.decode("utf-8", errors="replace")
                    for arg in cmdline.rstrip(b"\0").split(b"\0")]
        executable = os.readlink(proc / "exe")
        cmdline_after, truncated_after = _read_bounded(proc / "cmdline", 8192)
        executable_after = os.readlink(proc / "exe")
        if truncated_after or cmdline_after != cmdline or executable_after != executable:
            return {**result, "status": "PROCESS_EXEC_IDENTITY_CHANGED_DURING_READ",
                    "start_ticks": before["start_ticks"]}
        after = _proc_stat_identity(proc, pid)
        if (before["start_ticks"] != after["start_ticks"] or
                before["pgrp"] != after["pgrp"] or before["ppid"] != after["ppid"]):
            return {**result, "status": "PID_CHANGED_DURING_READ",
                    "start_ticks_before": before["start_ticks"],
                    "start_ticks_after": after["start_ticks"]}
        result.update({"start_ticks": before["start_ticks"],
                       "stat_state": before["state"], "ppid": before["ppid"],
                       "pgrp": before["pgrp"],
                       "argv_status": ("EXACT_ALLOWLISTED_COMMAND"
                                       if raw_argv == LIFELINE_EXPECTED_ARGV
                                       else "MISMATCH_REDACTED"),
                       "exe_status": ("EXACT_REVIEWED_PYTHON3"
                                      if executable == LIFELINE_EXPECTED_EXE
                                      else "MISMATCH_REDACTED"),
                       "identity_stable_during_read": True})
        if executable != LIFELINE_EXPECTED_EXE:
            result["status"] = "PROCESS_EXE_MISMATCH"
        return result
    except (OSError, ValueError, UnicodeError):
        return {**result, "status": "PROCESS_IDENTITY_UNREADABLE"}

def _lifeline_supervisor_config_fields(raw):
    out = {"parse_status": "CONFIG_INVALID_OR_UNREADABLE",
           "autostart": None, "autorestart": None,
           "command_matches_allowlist": None}
    if raw is None:
        return out
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        return out
    section = None
    found = {}
    duplicates = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if section != "program:nox-lifeline-guard" or "=" not in stripped:
            continue
        key, value = (part.strip() for part in stripped.split("=", 1))
        if key in ("autostart", "autorestart", "command"):
            if key in found:
                duplicates.add(key)
            found[key] = value
    if duplicates:
        out["parse_status"] = "DUPLICATE_CONFIG_KEYS"
        return out
    for key in ("autostart", "autorestart"):
        value = found.get(key, "").lower()
        out[key] = True if value == "true" else False if value == "false" else None
    expected_command = ("/usr/bin/python3 -u /root/nox/scripts/nox_native_lifeline.py "
                        "--policy /etc/nox/lifeline.json "
                        "--state /root/nox/state/lifeline/state.json")
    out["command_matches_allowlist"] = found.get("command") == expected_command
    out["parse_status"] = ("CONFIG_FIELDS_PARSED"
                           if out["autostart"] is not None and out["autorestart"] is not None
                           else "CONFIG_FIELDS_PARTIAL")
    return out

def _lifeline_cgroup_memory_snapshot():
    """Read only the two fixed cgroup-v2 scalars with a strict byte bound."""
    def scalar(path, allow_max=False):
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            fd = os.open(path, flags)
        except OSError:
            return None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                return None
            raw = os.read(fd, 65)
            after = os.fstat(fd)
            signature_before = (before.st_dev, before.st_ino, before.st_size,
                                before.st_mtime_ns, before.st_ctime_ns)
            signature_after = (after.st_dev, after.st_ino, after.st_size,
                               after.st_mtime_ns, after.st_ctime_ns)
            if (signature_before != signature_after or not raw or len(raw) > 64):
                return None
            raw = raw.removesuffix(b"\n")
            if allow_max and raw == b"max":
                return "max"
            return int(raw) if re.fullmatch(rb"(?:0|[1-9][0-9]{0,19})", raw) else None
        except (OSError, ValueError):
            return None
        finally:
            os.close(fd)

    current = scalar("/sys/fs/cgroup/memory.current")
    maximum = scalar("/sys/fs/cgroup/memory.max", allow_max=True)
    if type(current) is int and type(maximum) is int:
        headroom = maximum - current
        status = "OK" if headroom >= 0 else "INCONSISTENT"
        below = headroom < LIFELINE_MEMORY_FLOOR
    else:
        headroom = None
        status = "UNKNOWN"
        below = True
    return {"memory.current": current, "memory.max": maximum,
            "raw_headroom_bytes": headroom, "below_2GiB": below,
            "status": status}

def _lifeline_state_memory(raw, now=None):
    """Summarize persisted monitor telemetry without exporting state contents."""
    result = {"status": "UNKNOWN", "report_at": None, "age_seconds": None,
              "report_epoch": None,
              "memory.current": None, "memory.max": None,
              "raw_headroom_bytes": None, "below_2GiB": True}
    if raw is None:
        return result
    try:
        state = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_lifeline_unique_pairs,
                           parse_constant=_lifeline_reject_constant)
        report = state.get("last_report") if isinstance(state, dict) else None
        if (not isinstance(report, dict) or report.get("schema") != "NOX_LIFELINE_V2"
                or report.get("observer_only") is not True
                or not isinstance(report.get("at"), str)):
            return result
        timestamp = dt.datetime.fromisoformat(report["at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return result
        now = time.time() if now is None else now
        report_epoch = timestamp.timestamp()
        age = now - report_epoch
        memory = report.get("cgroup_memory")
        if not isinstance(memory, dict):
            return {**result, "report_at": report["at"], "report_epoch": report_epoch,
                    "age_seconds": round(age, 3),
                    "status": "UNKNOWN"}
        current, maximum = memory.get("memory.current"), memory.get("memory.max")
        headroom, below, status = (memory.get("raw_headroom_bytes"),
                                   memory.get("below_2GiB"), memory.get("status"))
        summary = {"report_at": report["at"], "report_epoch": report_epoch,
                   "age_seconds": round(age, 3),
                   "memory.current": current, "memory.max": maximum,
                   "raw_headroom_bytes": headroom, "below_2GiB": below}
        if (type(current) is int and type(maximum) is int and type(headroom) is int
                and type(below) is bool):
            expected = maximum - current
            expected_status = "OK" if expected >= 0 else "INCONSISTENT"
            if headroom != expected or below != (expected < LIFELINE_MEMORY_FLOOR) or status != expected_status:
                return {**summary, "status": "INCONSISTENT"}
            if age < -5:
                return {**summary, "status": "FUTURE_TIMESTAMP"}
            if age > LIFELINE_REPORT_MAX_AGE_SECONDS:
                return {**summary, "status": "STALE"}
            return {**summary, "status": "OK"}
        if (status == "UNKNOWN" and headroom is None and below is True
                and (type(current) is int or current is None)
                and (type(maximum) is int or maximum is None or maximum == "max")):
            if age < -5:
                return {**summary, "status": "FUTURE_TIMESTAMP"}
            if age > LIFELINE_REPORT_MAX_AGE_SECONDS:
                return {**summary, "status": "STALE"}
            return {**summary, "status": "UNKNOWN"}
        return {**summary, "status": "INCONSISTENT"}
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return result

def lifeline_evidence(binary=None, config=None):
    """Narrow read-only status + path hashes; never expose policy/state contents."""
    file_rows = {}
    raw_files = {}
    for label in ("script", "policy", "supervisor_config", "state"):
        file_rows[label], raw_files[label] = _lifeline_read_allowlisted_file(label)
    systemd = {}
    for field, args in (("active", ["systemctl", "is-active", "supervisor.service"]),
                        ("enabled", ["systemctl", "is-enabled", "supervisor.service"])):
        rc, output = run(args, seconds=10)
        systemd[field] = output.strip()[:40]
        systemd[field + "_rc"] = rc
    return {
        "schema": "NOX_LIFELINE_EVIDENCE_V1",
        "read_only": True,
        "file_contents_exported": False,
        "files": file_rows,
        "policy": _lifeline_policy_fields(raw_files.get("policy")),
        "supervisor_config": _lifeline_supervisor_config_fields(raw_files.get("supervisor_config")),
        "state_memory": _lifeline_state_memory(raw_files.get("state")),
        "cgroup_memory_now": _lifeline_cgroup_memory_snapshot(),
        "supervisor_systemd": systemd,
        "service": _lifeline_supervisor_service(binary, config),
    }

def lifeline_only(phase):
    """Low-overhead independent read-only pre/post Lifeline evidence mode."""
    if phase not in ("pre", "post", "auto"):
        raise ValueError("--lifeline-only requires --phase pre|post|auto")
    requested_phase = phase
    binary = shutil.which("supervisorctl")
    if not binary:
        binary = next((x for x in ("/opt/venv/bin/supervisorctl",
                                   "/usr/local/bin/supervisorctl") if Path(x).is_file()), None)
    candidates = [None] + [x for x in ("/etc/supervisor/supervisord.conf",
                                        "/etc/supervisord.conf",
                                        "/root/nox/supervisord.conf") if Path(x).is_file()]
    config = None
    if binary:
        for candidate in candidates:
            rc, output = run([binary] + (["-c", candidate] if candidate else []) + ["status"])
            if rc in (0, 3) and any(
                    re.match(r"^nox-lifeline-guard\s+", line)
                    for line in output.splitlines()):
                config = candidate
                break
    evidence = lifeline_evidence(binary, config)
    if phase == "auto":
        pre_service = evidence["service"]
        pre_systemd = evidence["supervisor_systemd"]
        pre_match = (
            evidence["files"].get("script", {}).get("sha256") == LIFELINE_PRE_SCRIPT_SHA256 and
            evidence["files"].get("supervisor_config", {}).get("sha256") == LIFELINE_PRE_CONFIG_SHA256 and
            evidence["files"].get("policy", {}).get("sha256") == LIFELINE_POLICY_SHA256 and
            evidence["policy"].get("enabled") is False and
            evidence["policy"].get("poll_seconds") == 60 and
            bool(evidence["policy"].get("restart_flags")) and
            all(flag is False for flag in evidence["policy"].get("restart_flags", {}).values()) and
            evidence["supervisor_config"].get("autostart") is False and
            evidence["supervisor_config"].get("autorestart") is True and
            pre_service.get("state") == "RUNNING" and
            pre_service.get("pid") == LIFELINE_PRE_GUARD_PID and
            pre_service.get("start_ticks") == LIFELINE_PRE_GUARD_START_TICKS and
            pre_service.get("argv_status") == "EXACT_ALLOWLISTED_COMMAND" and
            pre_service.get("exe_status") == "EXACT_REVIEWED_PYTHON3" and
            pre_service.get("identity_stable_during_read") is True and
            pre_systemd.get("active") == "active" and pre_systemd.get("active_rc") == 0 and
            pre_systemd.get("enabled") in ("enabled", "disabled") and
            pre_systemd.get("enabled_rc") == (0 if pre_systemd.get("enabled") == "enabled" else 1))
        post_fingerprint = (
            evidence["files"].get("script", {}).get("sha256") == LIFELINE_EXPECTED_SCRIPT_SHA256 and
            evidence["files"].get("supervisor_config", {}).get("sha256") == LIFELINE_RECONCILED_CONFIG_SHA256 and
            evidence["files"].get("policy", {}).get("sha256") == LIFELINE_POLICY_SHA256)
        if pre_match:
            phase = "pre"
        elif post_fingerprint:
            phase = "post"
        else:
            phase = "unknown"
    else:
        post_fingerprint = None
    status = "PRECHANGE_SNAPSHOT"
    if phase == "pre":
        current_memory = evidence["cgroup_memory_now"]
        if current_memory.get("status") != "OK":
            status = "PRECHANGE_MEMORY_UNKNOWN"
        else:
            status = ("PRECHANGE_LOW_MEMORY" if current_memory.get("below_2GiB")
                      else "PRECHANGE_MEMORY_OK")
    elif phase == "post":
        service = evidence["service"]
        memory = evidence["state_memory"]
        current_memory = evidence["cgroup_memory_now"]
        current_memory_valid = (
            current_memory.get("status") == "OK" and
            type(current_memory.get("memory.current")) is int and
            type(current_memory.get("memory.max")) is int and
            type(current_memory.get("raw_headroom_bytes")) is int and
            type(current_memory.get("below_2GiB")) is bool and
            current_memory["raw_headroom_bytes"] ==
            current_memory["memory.max"] - current_memory["memory.current"] and
            current_memory["below_2GiB"] ==
            (current_memory["raw_headroom_bytes"] < LIFELINE_MEMORY_FLOOR))
        if (service.get("state") == "RUNNING" and
                service.get("argv_status") == "EXACT_ALLOWLISTED_COMMAND" and
                service.get("exe_status") == "EXACT_REVIEWED_PYTHON3" and
                service.get("identity_stable_during_read") is True and
                evidence["supervisor_config"].get("autostart") is True and
                evidence["supervisor_config"].get("autorestart") is True and
                evidence["supervisor_config"].get("command_matches_allowlist") is True and
                evidence["policy"].get("enabled") is False and
                evidence["policy"].get("poll_seconds") == 60 and
                bool(evidence["policy"].get("restart_flags")) and
                all(flag is False for flag in evidence["policy"].get("restart_flags", {}).values()) and
                evidence["files"].get("policy", {}).get("sha256") == LIFELINE_POLICY_SHA256 and
                evidence["files"].get("supervisor_config", {}).get("sha256") ==
                LIFELINE_RECONCILED_CONFIG_SHA256 and
                evidence["supervisor_systemd"].get("active") == "active" and
                evidence["supervisor_systemd"].get("active_rc") == 0 and
                evidence["supervisor_systemd"].get("enabled") == "enabled" and
                evidence["supervisor_systemd"].get("enabled_rc") == 0 and
                evidence["files"].get("script", {}).get("sha256") == LIFELINE_EXPECTED_SCRIPT_SHA256 and
                memory.get("status") == "OK" and current_memory_valid):
            status = ("MONITOR_ACTIVE_LOW_MEMORY" if current_memory["below_2GiB"]
                      else "MONITOR_ACTIVE")
        else:
            status = ("POSTCHECK_MEMORY_UNKNOWN" if not current_memory_valid
                      else "POSTCHECK_HOLD")
    else:
        status = "AUTO_PHASE_HOLD"
    return {"schema": "NOX_LIFELINE_INDEPENDENT_AUDIT_V1",
            "read_only": True, "phase_requested": requested_phase, "phase": phase,
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "host_mutations": 0, "worker_pool_started": False,
            "read_only_subprocess_probes": True, "status": status,
            "evidence": evidence}

def supervisor():
    fence=v13_owner_fence_metadata()
    binary=shutil.which('supervisorctl')
    if not binary:
        binary=next((x for x in ('/opt/venv/bin/supervisorctl','/usr/local/bin/supervisorctl') if Path(x).is_file()),None)
    if not binary:return {'available':False,'owner_fence_readonly':fence,'lifeline_evidence':lifeline_evidence()}
    candidates=[None]+[x for x in ('/etc/supervisor/supervisord.conf','/etc/supervisord.conf','/root/nox/supervisord.conf') if Path(x).is_file()]
    results=[]
    for c in candidates:
        args=[binary]+(['-c',c] if c else [])+['status']
        rc,out=run(args)
        rows=[]
        for line in out.splitlines():
            m=re.match(r'^([A-Za-z0-9_.:-]+)\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)\b(.*)$',line)
            if m:
                pid=re.search(r'\bpid (\d+)',m.group(3))
                rows.append({'name':m.group(1),'state':m.group(2),'pid':int(pid[1]) if pid else None})
        results.append({'config':c,'rc':rc,'services':rows})
        if rows:break
    return {'available':True,'results':results,'owner_fence_readonly':fence,'lifeline_evidence':lifeline_evidence(binary, c)}

def v13_wheelhouse_admission(record):
    """Metadata-only ABI gate for the Drive CP311/cu126 wheelhouse, never an installer.

    A matching wheel tag is not a GPU smoke, driver test, license approval, or
    native installation receipt. Incompatible installed Python environments
    must not be modified to make a source check pass.
    """
    if not isinstance(record, dict) or not isinstance(record.get('_runtime'), dict):
        return 'HOLD_WHEELHOUSE_RUNTIME_ABI_UNKNOWN'
    runtime = record['_runtime']
    if runtime.get('python_abi') != 'cpython-311':
        return 'HOLD_WHEELHOUSE_CP311_PYTHON_ABI_MISMATCH'
    if runtime.get('platform') != 'linux-x86_64':
        return 'HOLD_WHEELHOUSE_LINUX_X86_64_PLATFORM_MISMATCH'
    # A CP311 cache tag alone is not enough: it can disagree with the
    # interpreter's actual version. Reject contradictory or missing evidence
    # rather than labelling a potentially CP312 process a candidate.
    python_version = runtime.get('python_version')
    if not isinstance(python_version, str) or re.fullmatch(r'3\.11\.\d+', python_version) is None:
        return 'HOLD_WHEELHOUSE_CP311_VERSION_MISMATCH'
    version = record.get('torch')
    if not isinstance(version, str) or not version:
        return 'HOLD_WHEELHOUSE_TORCH_BUILD_UNKNOWN'
    # A forged package label such as "unknown+cu126" is not a PyTorch build.
    if re.fullmatch(r'[1-9]\d*\.\d+\.\d+\+cu126', version) is None:
        return 'HOLD_WHEELHOUSE_CU126_TORCH_BUILD_MISMATCH'
    return 'SOURCE_ONLY_WHEELHOUSE_ABI_CANDIDATE_NATIVE_SM70_HOLD'


def packages():
    code="import importlib.metadata as m,json,sys,sysconfig; names=['torch','transformers','accelerate','datasets','deepspeed','safetensors','peft','bitsandbytes','trl','psutil','nvidia-ml-py','diffusers','opencv-python','imageio-ffmpeg']; d={'_runtime':{'python_abi':sys.implementation.cache_tag,'python_version':'.'.join(map(str,sys.version_info[:3])),'platform':sysconfig.get_platform()}};\nfor n in names:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
    found={}
    for p in ('/root/venv_volta/bin/python','/opt/venv/bin/python','/root/nox/.venv/bin/python','/usr/bin/python3'):
        if Path(p).is_file():
            rc,out=run([p,'-c',code])
            try:
                row=json.loads(out) if rc==0 else {'status':'IMPORT_FAILED'}
                if isinstance(row,dict) and rc==0:
                    row['_wheelhouse_candidate']=v13_wheelhouse_admission(row)
                found[p]=row
            except ValueError:found[p]={'status':'INVALID_OUTPUT'}
    return found

# Exact immutable DeepSeek pins mirrored from v51/hf_range_probe.py.
# The offline source test asserts these rows remain identical to that manifest.
MODEL_ROOT='/root/nox/models'
MODEL_MANIFEST_REVISION='65d53bc8be65123e255ff02f3ded958b6dbf54fd'
PINNED_MODEL_FILES=(
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf',5780704,'f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf',39535781184,'25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf',39736712000,'8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf',39036908384,'9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf',19923784832,'7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1'),
 ('DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf',110595290816,'3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3'),
)

def pinned_model_paths(root=MODEL_ROOT,lstat=os.lstat):
    """Metadata-only, no-follow stat for the six immutable targets under one root."""
    root_path=Path(root)
    if not root_path.is_absolute():
        return {'status':'HOLD_MODEL_ROOT_NOT_ABSOLUTE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,'files':[]}
    root_parts=root_path.parts
    ancestors=[]; current=Path(root_path.anchor)
    for part in root_parts[1:]:
        current=current/part
        ancestors.append(current)
    try:
        for ancestor in ancestors:
            mode=lstat(str(ancestor)).st_mode
            if __import__('stat').S_ISLNK(mode):
                return {'status':'HOLD_MODEL_PATH_SYMLINK','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_PATH_SYMLINK'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
            if not __import__('stat').S_ISDIR(mode):
                return {'status':'HOLD_MODEL_ROOT_COMPONENT_TYPE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_ROOT_COMPONENT_TYPE'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
    except FileNotFoundError:
        pass
    except OSError as exc:
        status='HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()
        return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                'files':[{'path':str(root_path/name),'exists':None,'type':'unknown',
                          'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                          'path_status':status} for name,size,_ in PINNED_MODEL_FILES]}
    results=[]
    for name,expected_bytes,sha256 in PINNED_MODEL_FILES:
        if (not name or Path(name).name!=name or '/' in name or '\\\\' in name
                or name in ('.','..')):
            return {'status':'HOLD_MODEL_PATH_ESCAPE','files':[]}
        target=root_path/name
        path=str(target)
        row={'path':path,'exists':False,'type':'missing','bytes':None,
             'expected_bytes':expected_bytes,'sha_status':'NOT_CHECKED'}
        try:
            observed=lstat(path)
            mode=observed.st_mode
            statmod=__import__('stat')
            if statmod.S_ISLNK(mode):
                row.update({'type':'symlink','path_status':'HOLD_MODEL_PATH_SYMLINK'})
                results.append(row)
                continue
            if statmod.S_ISREG(mode):
                row.update({'exists':True,'type':'regular','bytes':observed.st_size,
                            'size_status':'MATCH' if observed.st_size==expected_bytes else 'MISMATCH'})
            elif statmod.S_ISDIR(mode):
                row.update({'exists':True,'type':'directory','bytes':None})
            else:
                row.update({'exists':True,'type':'other','bytes':None})
            results.append(row)
        except FileNotFoundError:
            results.append(row)
        except OSError as exc:
            row.update({'type':'unknown','path_status':'HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()})
            results.append(row)
    # Overall status must fail closed. The caller must not treat unreadable, bad-sized,
    # or nonregular candidates as a clean model inventory just because other rows passed.
    path_holds=[r['path_status'] for r in results if r.get('path_status')]
    if 'HOLD_MODEL_PATH_SYMLINK' in path_holds:
        status='HOLD_MODEL_PATH_SYMLINK'
    elif path_holds:
        status=path_holds[0]
    elif any(r['type'] not in ('regular','missing') for r in results):
        status='HOLD_MODEL_TARGET_TYPE'
    elif any(r.get('size_status')=='MISMATCH' for r in results):
        status='HOLD_MODEL_FILE_SIZE_MISMATCH'
    elif any(r['type']=='missing' for r in results):
        # Missing GGUF files are not an admitted model, even if every readable
        # pathname was safe. In particular, never report OK for an empty root.
        status='HOLD_MODEL_FILES_MISSING'
    else:
        status='HOLD_MODEL_SHA_UNVERIFIED'  # File sizes match, but full GGUF SHA was NOT checked.
    return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
            'files':results}

def models():
    return {'pinned_model_paths':pinned_model_paths()}

def storage():
    rc=shutil.which('rclone')
    if not rc:return {'rclone_present':False}
    status,out=run([rc,'listremotes'])
    names=[x.strip() for x in out.splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:',x.strip())]
    checks=[]
    for remote in names[:3]:
        code,out=run([rc,'about',remote,'--json'],15)
        try:
            d=json.loads(out);clean={k:d[k] for k in ('total','used','free','trashed') if type(d.get(k)) is int}
        except (ValueError,TypeError):clean={}
        checks.append({'remote':remote,'about_rc':code,'capacity':clean})
    return {'rclone_present':True,'list_rc':status,'remotes':names,'checks':checks,
            'known_config_present':{x:Path(x).is_file() for x in ('/root/.config/rclone/rclone.conf','/root/nox/rclone.conf')}}

# Read only the current Linux mount namespace. Device source strings are intentionally
# omitted because they can contain remote paths or credentials. statvfs reads metadata only.
BLOCK_FILESYSTEMS={'ext2','ext3','ext4','xfs','btrfs','zfs','vfat','exfat','ntfs'}
LOCAL_CAPACITY_FILESYSTEMS=BLOCK_FILESYSTEMS|{'overlay','tmpfs','ramfs'}
def _unescape_mountinfo(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),value)

def _capacity_row(path,mount_rows,statvfs,path_exists):
    exists=bool(path_exists(path))
    matches=[r for r in mount_rows if path==r['mountpoint'] or path.startswith(r['mountpoint'].rstrip('/')+'/')]
    mount=max(matches,key=lambda r:len(r['mountpoint'])) if matches else None
    try:
        if not exists:raise FileNotFoundError(path)
        if mount is None or mount['filesystem'] not in LOCAL_CAPACITY_FILESYSTEMS:
            raise OSError('filesystem is outside the local capacity allowlist')
        st=statvfs(path); block_size=st.f_frsize or st.f_bsize
        total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
    except (OSError,AttributeError,TypeError,ValueError):
        total=None; available=None
    row={'path':path,'exists':exists,'mountpoint':mount['mountpoint'] if mount else None,
         'filesystem':mount['filesystem'] if mount else None,
         'device_major_minor':mount['device_major_minor'] if mount else None,
         'total_bytes':total,'available_bytes':available}
    return row

def _mount_inventory_from_text(text,statvfs=os.statvfs,path_exists=None):
    rows=[]; mount_by_path={}; type_counts={}
    lines=text.splitlines(); truncated=len(lines)>4096
    for line in lines[:4096]:
        try:
            before,after=line.split(' - ',1)
            left=before.split(); right=after.split()
            if len(left)<6 or len(right)<3:continue
            fstype=right[0]; mountpoint=_unescape_mountinfo(left[4]); dev=left[2]
            if not SAFE.fullmatch(mountpoint) or not re.fullmatch(r'\d+:\d+',dev):continue
            if re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}',fstype):
                type_counts[fstype]=type_counts.get(fstype,0)+1
            entry={'mountpoint':mountpoint,'filesystem':fstype,'device_major_minor':dev}
            mount_by_path[mountpoint]=entry
            if fstype in BLOCK_FILESYSTEMS and not any(r['mountpoint']==mountpoint for r in rows):
                try:
                    st=statvfs(mountpoint); block_size=st.f_frsize or st.f_bsize
                    total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
                except (OSError,AttributeError,TypeError,ValueError):
                    total=None; available=None
                rows.append({**entry,'total_bytes':total,'available_bytes':available})
        except (ValueError,IndexError):continue
    if len(rows)>512:
        rows=rows[:512]; truncated=True
    rows.sort(key=lambda r:(r['mountpoint'],r['filesystem'],r['device_major_minor']))
    if path_exists is None:path_exists=lambda p:Path(p).exists()
    all_mount_rows=list(mount_by_path.values())
    data_entry=mount_by_path.get('/data')
    paths=[_capacity_row(p,all_mount_rows,statvfs,path_exists) for p in ('/','/data','/workspace')]
    return {'scope':'current_process_mount_namespace_only','provider_disk_visibility':'not_established',
            'mountinfo_readable':True,'mountinfo_entry_count':len(lines),'filesystem_type_counts':type_counts,
            'data_mount_present':data_entry is not None,'data_mount_entry':data_entry,
            'storage_paths':paths,'eligible_block_mount_count':len(rows),'truncated':truncated,'mounts':rows}

def mount_inventory():
    try:
        text=Path('/proc/self/mountinfo').read_text()
    except OSError as e:
        return {'scope':'current_process_mount_namespace_only','mountinfo_readable':False,
                'error':type(e).__name__,'mounts':[]}
    return _mount_inventory_from_text(text)

def worker(i):
    try:
        functions=(hardware,process_rows,supervisor,packages,models,storage,mount_inventory)
        return {'section':functions[i].__name__,'worker_pid':os.getpid(),'result':functions[i]()}
    except Exception as e:return {'section':str(i),'worker_pid':os.getpid(),'error':type(e).__name__}

def main():
    if sys.argv[1:]:
        if len(sys.argv) == 4 and sys.argv[1] == "--lifeline-only" and sys.argv[2] == "--phase":
            result = lifeline_only(sys.argv[3])
            print("NOX_MAINT_AUDIT=" + json.dumps(result, separators=(",", ":")), flush=True)
            print("NOX_MAINT_AUDIT_COMPLETE=true", flush=True)
            return 0
        print("usage: owner_native_audit.py [--lifeline-only --phase pre|post]", file=sys.stderr)
        return 2
    if os.environ.get("NOX_LIFELINE_AUDIT_PHASE") == "auto":
        result = lifeline_only("auto")
        print("NOX_MAINT_AUDIT=" + json.dumps(result, separators=(",", ":")), flush=True)
        print("NOX_MAINT_AUDIT_COMPLETE=true", flush=True)
        return 0
    with ProcessPoolExecutor(max_workers=7) as pool:
        for row in pool.map(worker,range(7)):
            # One JSON record per bounded result item; never dump env/config secrets.
            print('NOX_MAINT_AUDIT='+json.dumps(row,separators=(',',':')),flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true',flush=True)
if __name__=='__main__':raise SystemExit(main())

