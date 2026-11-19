#!/usr/bin/env python3
"""Read-only root evidence before staging a dedicated Engram cold holder."""

import argparse
import configparser
import contextlib
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from engram_cold_holder import (
    Hold, HuggingFaceRedirect, OWNER_STOP_MARKERS, PARTS, REVISION, SIZE,
    preflight_egress,
)
from verify_ds41_backbone import MODEL, ROOT as BACKBONE, SHARDS, SOURCE_REVISION


SCHEMA = "NOX_COLD_STAGE_PREFLIGHT_V1"
INSTANCE = 60509551
SUP_CONFIG = "/etc/supervisor/supervisord.conf"
INCLUDES = "/etc/supervisor/conf.d"
MODEL_CONFIG_SHA = "07187b45fdeb8e1f8122e4fe47e797317a2db7feafea5e764564af0ad9f6f447"
MODEL_SECTION = "program:nox-ds41-8098"
HOLDER_SECTION = "program:nox-engram-cold-holder"
MODEL_GUARD = "/root/nox/ops/nox_boot_ds41_8098.sh"
MODEL_LAUNCHER = BACKBONE / "launch_ds41_8098_t119u.sh"
HOLDER_PATH = "/root/nox/ops/engram_cold_holder.py"
HOLDER_CONFIG = INCLUDES + "/nox-engram-cold-holder.conf"
OWNER_LEASE = Path("/root/nox/state/owner_maintenance.lock")
CP_ROOT = Path("/root/nox/lora/qwen35_9b/6907283384")
CP55 = "checkpoint-u00000055-a00000055-g01794833901774705882"
CP55_POINTER = "192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0"
CP55_MANIFEST = "458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65"
CP55_REQUIRED = {"adapter_model.safetensors", "adapter_config.json", "optimizer.pt",
                 "scheduler.pt", "scaler.pt", "rng_state.pt", "python_rng.json",
                 "student_state.json", "lineage.json"}
S03 = "/root/nox/kb/knowledge.sqlite"
QUEUE = "/root/nox/state/dispatcher/state.json"
JOURNAL = "/root/nox/state/dispatcher/queue.jsonl"
DISK_FS = {"overlay", "ext4", "xfs", "btrfs", "zfs", "f2fs"}
TEACHER = re.compile(rb"teacher|ds41[-_]teacher|qwen[^\r\n]{0,40}teacher", re.IGNORECASE)
SHA256 = re.compile(r"[0-9a-f]{64}")
SMALL = 256 << 10
DIRECTORY_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | os.O_CLOEXEC


class Invalid(ValueError):
    pass


def inode(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_ctime_ns, info.st_mtime_ns


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(condition):
    if not condition:
        raise Invalid()


@dataclass(frozen=True)
class Layout:
    root: Path = Path("/")
    proc: Path = Path("/proc")
    uid: int = 0
    gid: int = 0

    def trusted(self, info):
        check(info.st_uid == self.uid and not info.st_mode & 0o022)

    @contextlib.contextmanager
    def directory(self, logical):
        parts = Path(logical).parts
        check(parts and parts[0] == "/" and ".." not in parts)
        fd = os.open(self.root, DIRECTORY_FLAGS)
        try:
            self.trusted(os.fstat(fd))
            for part in parts[1:]:
                next_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                self.trusted(os.fstat(fd))
            yield fd
        finally:
            os.close(fd)

    def present(self, logical):
        path = Path(logical)
        with self.directory(path.parent) as directory:
            try:
                os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                return False
            return True

    def file(self, logical, *, limit=SMALL, prefix=None, gid=None):
        path = Path(logical)
        with self.directory(path.parent) as directory:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory)
            with os.fdopen(fd, "rb", buffering=0) as stream:
                before = os.fstat(fd)
                self.trusted(before)
                check(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                      and (gid is None or before.st_gid == gid))
                if prefix is None:
                    check(before.st_size <= limit)
                    data = stream.read(before.st_size + 1)
                    check(len(data) == before.st_size)
                else:
                    data = stream.read(prefix) if prefix else b""
                check(inode(os.fstat(fd)) == inode(before))
                check(inode(os.stat(path.name, dir_fd=directory, follow_symlinks=False)) == inode(before))
                return data, before.st_size

    def procfile(self, logical, limit=SMALL):
        with (self.proc / logical).open("rb", buffering=0) as stream:
            data = stream.read(limit + 1)
        check(len(data) <= limit)
        return data


def project_file(layout, path, expected):
    try:
        if not layout.present(path):
            return {"state": "ABSENT"}
        data, length = layout.file(path)
    except (OSError, Invalid):
        return {"state": "CONFLICT"}
    digest = sha(data)
    return {"state": "MATCH" if digest == expected else "CONFLICT",
            "sha256": digest, "size_bytes": length}


def onstart(layout, expected):
    info = project_file(layout, "/root/onstart.sh", expected)
    if info["state"] == "ABSENT":
        return {**info, "reviewed": expected is None}
    try:
        data, _ = layout.file("/root/onstart.sh")
        check(sha(data) == info.get("sha256"))
    except (OSError, Invalid):
        return {**info, "reviewed": False}
    supervisor = re.search(rb"supervisor(?:d|ctl)|conf\.d|nox-ds41-8098", data, re.I)
    edits = re.search(rb">|\b(?:sed|cp|mv|tee|install|truncate|rm|ln|cat)\b", data)
    return {**info, "reviewed": info["state"] == "MATCH", "teacher_reference": bool(TEACHER.search(data)),
            "supervisor_reference": bool(supervisor), "possible_config_overwrite": bool(supervisor and edits)}


def process(layout, pid):
    data = layout.procfile(f"{pid}/stat", 4096)
    leading, _, fields = data.rpartition(b") ")
    values = fields.split()
    check(leading.startswith(f"{pid} (".encode()) and len(values) >= 20 and values[0] != b"Z")
    return int(values[1]), int(values[19])


def supervisor_process(layout):
    init = process(layout, 1)
    check(init[0] == 0 and init[1] > 0)
    children = layout.procfile("1/task/1/children", 8192).split()
    check(len(children) <= 256 and all(child.isdigit() for child in children))
    candidates = []
    for pid in [1] + [int(child) for child in children]:
        try:
            args = layout.procfile(f"{pid}/cmdline", 16384).rstrip(b"\0").split(b"\0")
        except (FileNotFoundError, ProcessLookupError):
            continue
        names = [os.path.basename(arg) for arg in args[:2]]
        if not (names[0] == b"supervisord" or
                (names[0].startswith(b"python") and len(names) > 1 and names[1] == b"supervisord")):
            continue
        options = []
        for index, arg in enumerate(args):
            if arg in (b"-c", b"--configuration"):
                options.append(args[index + 1: index + 2] or [b""])
            elif arg.startswith(b"--configuration="):
                options.append([arg.partition(b"=")[2]])
        check(options == [[SUP_CONFIG.encode()]])
        parent, ticks = process(layout, pid)
        check(parent == (0 if pid == 1 else 1) and ticks >= init[1])
        candidates.append((pid, ticks))
    check(len(candidates) == 1)
    pid, ticks = candidates[0]
    check(process(layout, 1) == init and process(layout, pid)[1] == ticks)
    return {"pid1_start_ticks": init[1], "supervisor_pid": pid, "supervisor_start_ticks": ticks,
            "configuration_explicit": True, "parent_pid1": pid != 1}


def config(data):
    parsed = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(";",))
    parsed.read_string(data.decode("utf-8"))
    check(not parsed.defaults())
    return parsed


def supervisor(layout, guard_sha, launcher_sha):
    runtime = supervisor_process(layout)
    main, _ = layout.file(SUP_CONFIG)
    sections = config(main)
    check(sections.get("include", "files", fallback="").split() in
          [["conf.d/*.conf"], [INCLUDES + "/*.conf"]])
    with layout.directory(INCLUDES) as directory, os.scandir(directory) as entries:
        names = []
        for i, entry in enumerate(entries):
            check(i < 256)
            if entry.name.endswith(".conf"):
                names.append(entry.name)
    all_configs = [(SUP_CONFIG, main)] + [(f"{INCLUDES}/{name}", layout.file(f"{INCLUDES}/{name}")[0])
                                         for name in sorted(names)]
    model_configs = []
    holder_configs = []
    teacher_autostart = False
    for path, data in all_configs:
        parsed = config(data)
        if parsed.has_section(MODEL_SECTION):
            model_configs.append((sha(data), parsed[MODEL_SECTION]))
        if parsed.has_section(HOLDER_SECTION):
            holder_configs.append(path)
        for section in parsed.sections():
            if section.startswith("group:"):
                names = parsed[section].get("programs", "").replace(" ", "").split(",")
                check(MODEL_SECTION[8:] not in names and HOLDER_SECTION[8:] not in names)
            if section.startswith("program:") and TEACHER.search(section.encode()):
                teacher_autostart |= parsed[section].getboolean("autostart", True)
    check(len(model_configs) == 1 and holder_configs in ([], [HOLDER_CONFIG]))
    found_sha, model = model_configs[0]
    command = model.get("command", "").split()
    guard, guard_size = layout.file(MODEL_GUARD)
    launcher, launcher_size = layout.file(MODEL_LAUNCHER)
    launch_known = (sha(guard) == guard_sha and sha(launcher) == launcher_sha
                    and command == ["/bin/bash", MODEL_GUARD] and model.getboolean("autostart", True)
                    and b"/root/nox/models/engram_ram.gguf" in guard and str(SIZE).encode() in guard
                    and str(MODEL_LAUNCHER).encode() in guard)
    return {**runtime, "main_config_sha256": sha(main), "model_config_sha256": found_sha,
            "model_guard_sha256": sha(guard), "model_guard_size_bytes": guard_size,
            "model_launcher_sha256": sha(launcher), "model_launcher_size_bytes": launcher_size,
            "model_startup_attested": launch_known and found_sha == MODEL_CONFIG_SHA,
            "teacher_autostart": teacher_autostart, "holder_service_declared": bool(holder_configs)}


def disk_filesystem(mounts, path):
    match = None
    for line in mounts.splitlines():
        mount, separator, description = line.partition(b" - ")
        fields = mount.split()
        if not separator or len(fields) < 6 or not description.split():
            continue
        target = re.sub(rb"\\([0-7]{3})", lambda value: bytes([int(value[1], 8)]), fields[4])
        if path == target or path.startswith(target.rstrip(b"/") + b"/"):
            if match is None or len(target) >= match[0]:
                match = len(target), description.split()[0].decode("ascii")
    check(match is not None)
    return match[1] in DISK_FS


def json_record(layout, path, maximum=SMALL):
    raw, length = layout.file(path, limit=maximum)
    value = json.loads(raw)
    check(isinstance(value, dict))
    return value, sha(raw), length


def persistent(layout):
    mounts = layout.procfile("self/mountinfo", 1 << 20)
    shards = []
    for index, (expected_size, expected_sha) in enumerate(SHARDS, 1):
        path = BACKBONE / f"{MODEL}-{index:05d}-of-00006.gguf"
        magic, length = layout.file(path, prefix=4)
        shards.append({"length_bytes": length, "expected_sha256": expected_sha,
                       "present": magic == b"GGUF" and length == expected_size
                       and disk_filesystem(mounts, os.fsencode(path))})
    pointer_path = CP_ROOT / "latest_checkpoint.json"
    manifest_path = CP_ROOT / CP55 / "checkpoint_manifest.json"
    pointer, pointer_sha, pointer_size = json_record(layout, pointer_path)
    manifest, manifest_sha, manifest_size = json_record(layout, manifest_path)
    checkpoint = (pointer_sha == CP55_POINTER and pointer.get("directory") == CP55
                  and pointer.get("manifest_sha256") == manifest_sha == CP55_MANIFEST
                  and all(disk_filesystem(mounts, os.fsencode(path)) for path in (pointer_path, manifest_path)))
    files = manifest.get("files_sha256")
    checkpoint &= (manifest.get("schema") == "NOX_QWEN35_9B_CHECKPOINT_V1"
                   and manifest.get("directory") == CP55 and isinstance(files, dict)
                   and CP55_REQUIRED <= files.keys() and len(files) <= 32
                   and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", name)
                           and name != "checkpoint_manifest.json" and isinstance(pin, str)
                           and SHA256.fullmatch(pin) for name, pin in files.items()))
    checkpoint_bytes = 0
    if checkpoint:
        for name in files:
            payload_path = manifest_path.parent / name
            _, payload_size = layout.file(payload_path, prefix=0)
            checkpoint &= payload_size > 0 and disk_filesystem(mounts, os.fsencode(payload_path))
            checkpoint_bytes += payload_size
        checkpoint &= 0 < checkpoint_bytes <= 2 << 30
    header, sqlite_size = layout.file(S03, prefix=16)
    database = header == b"SQLite format 3\0" and sqlite_size >= 100 and disk_filesystem(mounts, os.fsencode(S03))
    wal = S03 + "-wal"
    wal_present = layout.present(wal)
    wal_size = layout.file(wal, prefix=0)[1] if wal_present else 0
    database &= not wal_present or disk_filesystem(mounts, os.fsencode(wal))
    queue, queue_sha, queue_size = json_record(layout, QUEUE, maximum=16 << 20)
    tasks = queue.get("tasks")
    check(isinstance(tasks, dict) and bool(tasks))
    for row in tasks.values():
        check(isinstance(row, dict) and isinstance(row.get("status"), str))
    owners = ("claim", "owner_claim", "native_worker_lease", "claimed_by")
    active = any(row["status"].lower() in ("running", "in_progress", "executing", "claimed")
                 or any(row.get(key) for key in owners) for row in tasks.values())
    _, journal_length = layout.file(JOURNAL, prefix=0)
    queue_present = journal_length > 0 and all(disk_filesystem(mounts, os.fsencode(path))
                                                for path in (QUEUE, JOURNAL))
    stage_directories = all(disk_filesystem(mounts, os.fsencode(Path(path).parent))
                            for path in (HOLDER_PATH, HOLDER_CONFIG))
    lease_ok = False
    try:
        layout.file(OWNER_LEASE, prefix=0, gid=layout.gid)
        lease_ok = True
    except (OSError, Invalid):
        pass
    owner_stop = False
    owner_flags = ["/root/nox/" + flag for flag in OWNER_STOP_MARKERS]
    for flag in [*owner_flags, "/workspace/NOX_STOP"]:
        try:
            owner_stop |= layout.present(flag)
        except FileNotFoundError:
            continue
    return {"backbone": {"revision": SOURCE_REVISION, "parts": shards,
                         "present": all(part["present"] for part in shards),
                         "full_payload_hashes_verified": False},
            "checkpoint": {"metadata_matches": checkpoint, "pointer_sha256": pointer_sha,
                           "pointer_size_bytes": pointer_size, "manifest_sha256": manifest_sha,
                           "manifest_size_bytes": manifest_size, "payload_size_bytes": checkpoint_bytes,
                           "full_payload_hashes_verified": False},
            "s03": {"present": database, "size_bytes": sqlite_size, "wal_present": wal_present,
                    "wal_size_bytes": wal_size, "restore_verified": False},
            "queue": {"present": queue_present, "state_sha256": queue_sha, "state_size_bytes": queue_size,
                      "journal_size_bytes": journal_length, "active_claims": active},
            "owner_stop_marker_present": owner_stop, "owner_lease_trusted": lease_ok,
            "stage_directories_persistent": stage_directories,
            "present": all(part["present"] for part in shards) and checkpoint and database and queue_present}


def scoped_egress(opener):
    result = preflight_egress(opener)
    for row, part in zip(result["parts"], PARTS, strict=True):
        row["expected_sha256"] = part.sha256
    return result


def inspect_only(function, *args):
    try:
        return function(*args)
    except (OSError, Invalid, Hold, TypeError, ValueError, configparser.Error, urllib.error.URLError):
        return {"verified": False}


def collect(args, *, layout=Layout(), opener=None, container_label=None, container_id=None):
    identity_present = bool(container_label or container_id)
    correct_label = container_label in (None, "", f"C.{INSTANCE}", str(INSTANCE))
    correct_id = container_id in (None, "", str(INSTANCE))
    bound = ((os.geteuid(), os.getegid()) == (layout.uid, layout.gid) and args.instance_id == INSTANCE
             and identity_present and correct_label and correct_id)
    report = {"schema": SCHEMA, "instance_id": args.instance_id, "instance_bound": bound,
              "source_sha": args.source_sha, "request_id": args.request_id,
              "stage_eligible": False, "reboot_verified": False, "checks": {}}
    if not bound:
        return report
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), HuggingFaceRedirect())
    checks = report["checks"]
    checks["onstart"] = onstart(layout, args.onstart_sha256)
    checks["supervisor"] = inspect_only(supervisor, layout, args.guard_sha256, args.launcher_sha256)
    checks["staged_pair"] = {
        "holder": project_file(layout, HOLDER_PATH, args.holder_sha256),
        "config": project_file(layout, HOLDER_CONFIG, args.config_sha256),
    }
    checks["egress"] = inspect_only(scoped_egress, opener)
    checks["persistent"] = inspect_only(persistent, layout)
    states = tuple(checks["staged_pair"][part]["state"] for part in ("holder", "config"))
    supervisor_ok = (checks["supervisor"].get("model_startup_attested") is True
                     and checks["supervisor"].get("teacher_autostart") is False
                     and checks["supervisor"].get("holder_service_declared") == (states == ("MATCH", "MATCH")))
    report["stage_eligible"] = bool(
        checks["onstart"].get("reviewed") and not checks["onstart"].get("possible_config_overwrite")
        and not checks["onstart"].get("teacher_reference") and supervisor_ok and
        states in (("ABSENT", "ABSENT"), ("MATCH", "MATCH")) and
        checks["egress"].get("egress_reachable") and checks["persistent"].get("present")
        and checks["persistent"].get("owner_lease_trusted")
        and checks["persistent"].get("stage_directories_persistent")
    )
    return report


def parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", type=int, required=True, choices=[INSTANCE])
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--source-sha", required=True)
    for pin in ("onstart", "guard", "launcher", "holder", "config"):
        parser.add_argument(f"--{pin}-sha256", required=pin in ("holder", "config"))
    args = parser.parse_args()
    if (not re.fullmatch(r"[0-9a-f]{40}", args.source_sha)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", args.request_id)
            or any(not SHA256.fullmatch(value) for key, value in vars(args).items()
                   if key.endswith("_sha256") and value is not None)):
        parser.error("expected exact hexadecimal source and payload pins and a numeric owner request")
    return args


def main():
    result = collect(parse(), container_label=os.environ.get("VAST_CONTAINERLABEL"),
                     container_id=os.environ.get("CONTAINER_ID"))
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0 if result["stage_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
