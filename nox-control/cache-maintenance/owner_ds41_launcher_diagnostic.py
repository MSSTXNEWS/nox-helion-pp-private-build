"""Read-only DS4.1 cold launcher provenance, path shape and guard projection."""

import hashlib
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path, PurePosixPath


INSTANCE = 60509551
MODEL_GUARD = "/root/nox/ops/nox_boot_ds41_8098.sh"
GUARD_SHA256 = "b280bc46218d37a1480680a3d842c9b53d71a3d567c07606a1fb54878188d777"
MODEL_DIR = "/root/nox/models/deepseek_v41_flash_iq2xxs"
CANONICAL = MODEL_DIR + "/launch_ds41_8098_t119u.sh"
# The only launcher path attested in the Drive canon. No unknown alias is opened.
APPROVED_LAUNCHER_TARGETS = frozenset({CANONICAL})
MAX_SOURCE_BYTES = 128 << 10
EXPECTED_ENGRAM_SIZE = b"75266239716"
ENGRAM = b"/root/nox/models/engram_ram.gguf"
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC


class Invalid(ValueError):
    pass


def owner():
    return 0, 0


def need(condition):
    if not condition:
        raise Invalid()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_ctime_ns, info.st_mtime_ns)


def parent_directory(stack, root, logical):
    current = root
    path = PurePosixPath(logical)
    for part in path.parent.parts[1:]:
        current = os.open(part, DIR_FLAGS, dir_fd=current)
        stack.callback(os.close, current)
        info = os.fstat(current)
        need((info.st_uid, info.st_gid) == owner() and not info.st_mode & 0o022)
    return current, path.name


def clean_target(link, raw):
    """One absolute or a same-directory basename; never normalize dot components."""
    components = raw.split("/")
    if raw.startswith("/"):
        components = components[1:]
        prefix = "/"
    else:
        if len(components) != 1:
            return None
        prefix = str(PurePosixPath(link).parent) + "/"
    if not components or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", part)
                             for part in components):
        return None
    return prefix + "/".join(components)


def path_facts(root, logical, *, allow_alias, seen=frozenset()):
    row = {"present": False, "scope": "UNAVAILABLE", "bytes_read": 0}
    try:
        with ExitStack() as stack:
            parent, name = parent_directory(stack, root, logical)
            initial = os.stat(name, dir_fd=parent, follow_symlinks=False)
            mode = initial.st_mode
            row = {"present": True, "is_regular": stat.S_ISREG(mode),
                   "is_symlink": stat.S_ISLNK(mode), "mode": stat.S_IMODE(mode),
                   "owner_uid": initial.st_uid, "owner_gid": initial.st_gid,
                   "link_count": initial.st_nlink, "size_bytes": initial.st_size,
                   "group_world_write": bool(mode & 0o022), "bytes_read": 0}
            if stat.S_ISLNK(mode):
                need(allow_alias and (initial.st_uid, initial.st_gid) == owner())
                raw_target = os.readlink(name, dir_fd=parent)
                need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(initial))
                clean = clean_target(logical, raw_target)
                row.update(scope="PROTECTED_ALIAS", lexical_target_clean=clean is not None,
                           target_sha256=sha(os.fsencode(raw_target)),
                           target_in_model_directory=bool(clean and PurePosixPath(clean).parent == PurePosixPath(MODEL_DIR)),
                           exact_target_approved=clean in APPROVED_LAUNCHER_TARGETS, target_followed=False)
                if clean in APPROVED_LAUNCHER_TARGETS and clean not in seen | {logical}:
                    target, data = path_facts(root, clean, allow_alias=False, seen=seen | {logical})
                    row.update(scope="APPROVED_ALIAS", target_followed=True, target=target)
                    return row, data
                return row, b""
            if (not stat.S_ISREG(mode) or (initial.st_uid, initial.st_gid) != owner()
                    or mode & 0o7022 or initial.st_nlink != 1
                    or not 0 < initial.st_size <= MAX_SOURCE_BYTES):
                row["scope"] = "PROTECTED_FILE_METADATA"
                return row, b""
            descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
            with os.fdopen(descriptor, "rb") as stream:
                need(stamp(os.fstat(descriptor)) == stamp(initial))
                raw = stream.read(initial.st_size + 1)
                need(len(raw) == initial.st_size and stamp(os.fstat(descriptor)) == stamp(initial))
            need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(initial))
            row.update(scope="TRUSTED_REGULAR", bytes_read=len(raw), sha256=sha(raw),
                       executable_by_owner=bool(mode & 0o100))
            return row, raw
    except (Invalid, OSError):
        return {**row, "scope": "UNAVAILABLE_OR_UNTRUSTED"}, b""


def exec_style(raw):
    if len(re.findall(rb"(?m)^[ \t]*exec[ \t]+", raw)) != 1:
        return "UNVERIFIED"
    pathname = re.escape(CANONICAL.encode())
    target = rb"(?:'" + pathname + rb"'|\"" + pathname + rb"\"|" + pathname + rb")"
    assignment = re.findall(rb"(?m)^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z_0-9]*)=" + target
                            + rb"(?:[ \t]|$)", raw)
    if len(assignment) == 1:
        name = re.escape(assignment[0])
        assignments_for_name = re.findall(rb"(?m)^[ \t]*(?:export[ \t]+)?" + name + rb"=", raw)
        if len(assignments_for_name) == 1:
            var = rb"\$(?:" + name + rb"|\{" + name + rb"\})"
            target = rb"(?:" + target + rb"|\"" + var + rb"\"|" + var + rb")"
    direct = rb"(?m)^[ \t]*exec[ \t]+" + target + rb"(?=[ \t;&]|$)"
    bash = rb"(?m)^[ \t]*exec[ \t]+/bin/(?:bash|sh)[ \t]+" + target + rb"(?=[ \t;&]|$)"
    if re.search(direct, raw):
        return "DIRECT"
    if re.search(bash, raw):
        return "SHELL_INTERPRETER"
    return "UNVERIFIED"


def guard_facts(raw):
    active = b"\n".join(line for line in raw.splitlines() if not line.lstrip().startswith(b"#"))
    return {"guard_pin_matches": bool(raw) and sha(raw) == GUARD_SHA256,
            "engram_path_reference": ENGRAM in active,
            "exact_size_reference": bool(re.search(rb"(?<!\d)" + EXPECTED_ENGRAM_SIZE + rb"(?!\d)", active)),
            "file_stat_reference": bool(re.search(rb"(?<![-A-Za-z])stat(?:[\s;]|$)", active)),
            "while_until_loop_present": bool(re.search(rb"(?m)^[ \t]*(?:while|until)[ \t]", active)),
            "sleep_30s_reference": bool(re.search(rb"\bsleep[ \t]+(?:30|30s)(?:[\s;]|$)", active)),
            "time_limit_reference": bool(re.search(rb"(?i)\b(?:timeout|deadline|max_attempts|end_time|SECONDS)\b", active)),
            "training_guard_reference": bool(re.search(rb"TRAIN_T131U_STATUS|train_wants_gpu1|training_status", active)
                                             and re.search(rb"TRAINING|RUNNING", active)),
            "exact_launcher_exec_style": exec_style(active)}


def provider_witness():
    identity = os.environ.get("CONTAINER_ID", "")
    label = os.environ.get("VAST_CONTAINERLABEL", "")
    return bool(identity or label) and identity in ("", str(INSTANCE)) and label in (
        "", str(INSTANCE), f"C.{INSTANCE}",
    )


def project(*, instance_id, expected_launcher_sha256=None, root=Path("/")):
    bound = instance_id == INSTANCE and (os.geteuid(), os.getegid()) == owner() and provider_witness()
    result = {"instance_bound": bound,
              "launcher_pin_matches": False, "trusted_existing_launch_candidate": False,
              "runtime_mutated": False, "restart_verified": False}
    if not result["instance_bound"]:
        return result
    descriptor = os.open(root, DIR_FLAGS)
    try:
        root_info = os.fstat(descriptor)
        need((root_info.st_uid, root_info.st_gid) == owner() and not root_info.st_mode & 0o022)
        guard_path, guard_raw = path_facts(descriptor, MODEL_GUARD, allow_alias=False)
        launcher, launcher_raw = path_facts(descriptor, CANONICAL, allow_alias=True)
    finally:
        os.close(descriptor)
    guard = guard_facts(guard_raw)
    approved_pin = isinstance(expected_launcher_sha256, str) and re.fullmatch("[0-9a-f]{64}", expected_launcher_sha256)
    launcher_pin_matches = bool(launcher_raw and approved_pin and sha(launcher_raw) == expected_launcher_sha256)
    actual = launcher["target"] if launcher["scope"] == "APPROVED_ALIAS" else launcher
    usable = (guard["guard_pin_matches"] and guard["engram_path_reference"] and guard["exact_size_reference"]
              and guard["file_stat_reference"] and launcher_pin_matches
              and (guard["exact_launcher_exec_style"] == "SHELL_INTERPRETER"
                   or (guard["exact_launcher_exec_style"] == "DIRECT" and actual.get("executable_by_owner"))))
    result.update(guard_path=guard_path, guard_policy=guard, launcher=launcher,
                  launcher_pin_matches=launcher_pin_matches, trusted_existing_launch_candidate=bool(usable))
    return result
