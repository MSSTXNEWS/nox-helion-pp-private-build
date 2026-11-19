"""Read-only source evidence for the exact NOX cold Supervisor startup chain."""

import configparser
from contextlib import ExitStack
import hashlib
import json
import os
import re
import shlex
import stat
from pathlib import Path, PurePosixPath


STARTUP = "/root/onstart.sh"
MAIN = "/etc/supervisor/supervisord.conf"
INCLUDE = "/etc/supervisor/conf.d"
HOLDER = INCLUDE + "/nox-engram-cold-holder.conf"
MODEL = INCLUDE + "/nox-ds41-8098.conf"
DISPATCHER = INCLUDE + "/nox-t855u.conf"
HOLDER_SOURCE = "/root/nox/ops/engram_cold_holder.py"
MODEL_GUARD = "/root/nox/ops/nox_boot_ds41_8098.sh"
MODEL_LAUNCHER = "/root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh"
DISPATCHER_SERVICE = "nox-dispatcher-t855u"
BOOT_BACKUP = "/root/onstart.sh.nox-pre-dispatcher-b36b916aadc8"
BOOT_CANDIDATE = "e3e79973beb6291f5d33c3e79cff12e7e849ddef2fb1e30b897ace9a3f695115"
INSTALL_EPOCH = 167790899
STARTUP_PINS = {
    STARTUP: "b36b916aadc8bb6047108823bf7b86f00448deafd9f79a824a9f4924c1190507",
    BOOT_BACKUP: "b36b916aadc8bb6047108823bf7b86f00448deafd9f79a824a9f4924c1190507",
    MAIN: "fcead12b4dcb7f56b31d223f1cfa89792bd6e8008f78708a831b41fab9ece25d",
    HOLDER: "cc7a0c2ddb579005bf9a6cdd6ccac9e33f1010039f6b2fe984f1059655b036df",
    MODEL: "07187b45fdeb8e1f8122e4fe47e797317a2db7feafea5e764564af0ad9f6f447",
    DISPATCHER: "4c871669f0b6618221585592c80040acab1acdd6b3ff5d659229fc008d894e73",
    HOLDER_SOURCE: "3ec79df376490c37300eb7ec78b5feb59463bc5abd976093331e5c305d4c62de",
    MODEL_GUARD: "b280bc46218d37a1480680a3d842c9b53d71a3d567c07606a1fb54878188d777",
    MODEL_LAUNCHER: "50a4e198bcfed2e7965220e897c349db50eb17dd9560243827c9a085923e6638",
}
SUPERVISOR_REFERENCE = re.compile(
    r"supervisord|supervisorctl|/etc/supervisor(?:/|\b)|conf\.d/|nox-t855u|nox-dispatcher-t855u"
    r"|nox-ds41-8098|nox-engram-cold-holder"
)
LITERAL_ASSIGNMENT = re.compile(r"(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)")
LITERAL_HEREDOC = re.compile(
    r"[ \t]*cat[ \t]*>[ \t]*(/etc/supervisor/[A-Za-z0-9_./-]+)[ \t]+<<[ \t]*"
    r"(['\"])([A-Za-z_][A-Za-z0-9_]{0,47})\2[ \t]*"
)
DYNAMIC_HELPER = re.compile(r"^(?:source\s|\.\s|eval\s|(?:/bin/)?(?:bash|sh)\s+-[a-z]*c\s)")
MAX_BYTES = 128 << 10
MAX_LINES = 256
MUTATORS = {"cp", "install", "ln", "mv", "rm", "tee", "truncate", "touch", "chmod", "chown", "rmdir"}
OUTPUT = {">", ">>", ">|", "&>", "&>>", "<>"}
SEPARATORS = {";", "&&", "||", "|", "(", ")"}
SCOPES = {MAIN: "MAIN", INCLUDE: "INCLUDE_DIR", HOLDER: "HOLDER", MODEL: "MODEL", DISPATCHER: "DISPATCHER"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def config(raw):
    parsed = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(";",))
    try:
        parsed.read_string(raw.decode("utf-8"))
    except (ValueError, configparser.Error):
        return None
    return parsed if not parsed.defaults() else None


def config_word(word):
    return word == "/etc/supervisor" or word.startswith("/etc/supervisor/")


def shell_words(line):
    lexer = shlex.shlex(line, posix=True, punctuation_chars="();<>|&")
    lexer.whitespace_split = True
    return list(lexer)


def classify(line, aliases):
    assignment = LITERAL_ASSIGNMENT.fullmatch(line.strip())
    if assignment:
        name, value = assignment.groups()
        values = shell_words(value)
        if len(values) == 1 and re.fullmatch(r"/etc/supervisor(?:/[A-Za-z0-9_.-]+)*", values[0]):
            if name in aliases:
                aliases[name] = None
                return "DYNAMIC_REFERENCE", []
            aliases[name] = values[0]
            return "LITERAL_PATH_ASSIGNMENT", [values[0]]
    words = shell_words(line)
    resolved = []
    for word in words:
        if word.startswith("--configuration="):
            resolved.extend(("--configuration", word.partition("=")[2]))
        else:
            reference = re.fullmatch(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))", word)
            variable = next((part for part in reference.groups() if part), "") if reference else ""
            resolved.append(aliases.get(variable) or word)
    if not resolved:
        return "NO_COMMAND", []
    paths = [word for word in resolved if config_word(word)]
    first = 1 if resolved[0] == "exec" and len(resolved) > 1 else 0
    command = PurePosixPath(resolved[first]).name
    if any(value in SEPARATORS for value in resolved):
        return "COMPOUND_REFERENCE", paths
    if any(i and config_word(word) and resolved[i - 1] in OUTPUT for i, word in enumerate(resolved)):
        return "CONFIG_WRITE", paths
    if command in MUTATORS or (command == "sed" and any(word.startswith("-i") for word in resolved[1:])):
        return "CONFIG_MUTATION_RISK", paths
    if command == "mkdir" and resolved[1:2] == ["-p"] and paths and len(paths) == len(resolved) - 2:
        if all(path in ("/etc/supervisor", INCLUDE) for path in paths):
            return "CREATE_INCLUDE_DIRECTORIES_ONLY", paths
    if command == "supervisord":
        options = [resolved[i + 1] for i, item in enumerate(resolved[:-1]) if item in ("-c", "--configuration")]
        if options == [MAIN]:
            return ("SUPERVISOR_EXEC_EXACT_MAIN" if first else "SUPERVISOR_STARTS_EXACT_MAIN"), paths
    if command == "supervisorctl":
        args = resolved[first + 1:]
        if args[:2] == ["-c", MAIN] or args[:2] == ["--configuration", MAIN]:
            args = args[2:]
        if args == ["start", DISPATCHER_SERVICE]:
            return "DISPATCHER_START_REFERENCE", paths
        if args and args[0] in ("status", "pid"):
            return "SUPERVISOR_READ", paths
    return "UNCLASSIFIED_REFERENCE", paths


def startup_facts(raw, pinned):
    facts = {"startup_literal_reference_facts": [], "supervisor_config_write_risk_count": 0,
             "supervisor_reference_unclassified_count": 0, "indirect_shell_reference_count": 0,
             "runtime_startup_verified": False}
    try:
        rows = raw.decode("utf-8").splitlines(keepends=True)
    except ValueError:
        return facts
    if not rows or len(rows) > MAX_LINES or any(len(row) > 4096 for row in rows):
        return facts
    lines = iter(enumerate(rows, 1))
    aliases = {}
    for number, row in lines:
        stripped = row.lstrip()
        if stripped.startswith("#"):
            continue
        if DYNAMIC_HELPER.search(stripped) or "$(" in row or "`" in row:
            facts["indirect_shell_reference_count"] += 1
        exact_template = LITERAL_HEREDOC.fullmatch(row.rstrip("\r\n"))
        if exact_template:
            path, _, delimiter = exact_template.groups()
            body = []
            for _, item in lines:
                if item.rstrip("\r\n") == delimiter:
                    break
                body.append(item)
            else:
                facts["supervisor_reference_unclassified_count"] += 1
                break
            preserved = path in (MAIN, HOLDER, MODEL, DISPATCHER) and pinned.get(path) == "".join(body).encode()
            category = "IDENTICAL_LITERAL_CONFIG_TEMPLATE" if preserved else "CONFIG_WRITE"
            targets = [path]
        elif SUPERVISOR_REFERENCE.search(row) or any("$" + name in row or "${" + name + "}" in row
                                                     for name in aliases):
            try:
                category, targets = classify(row, aliases)
            except ValueError:
                category, targets = "UNCLASSIFIED_REFERENCE", []
        elif (assignment := LITERAL_ASSIGNMENT.fullmatch(row.strip())) and assignment[1] in aliases:
            aliases[assignment[1]] = None
            category, targets = "DYNAMIC_REFERENCE", []
        else:
            continue
        facts["startup_literal_reference_facts"].append({
            "line": number, "sha256": sha(row.encode()), "kind": category,
            "scopes": sorted({SCOPES.get(path, "OTHER_SUPERVISOR_PATH") for path in targets}),
        })
        if category in ("CONFIG_WRITE", "CONFIG_MUTATION_RISK"):
            facts["supervisor_config_write_risk_count"] += 1
        if category in ("COMPOUND_REFERENCE", "DYNAMIC_REFERENCE", "UNCLASSIFIED_REFERENCE"):
            facts["supervisor_reference_unclassified_count"] += 1
    return facts


def unit(raw, service):
    parsed = config(raw)
    section = "program:" + service
    if parsed is None or not parsed.has_section(section):
        return None
    entry = parsed[section]
    try:
        return {"autostart": entry.getboolean("autostart", fallback=True),
                "priority": entry.getint("priority", fallback=999),
                "command": entry.get("command", "").split()}
    except ValueError:
        return None


def project(read):
    """Caller supplies the existing trusted bounded root-file reader by exact path."""
    evidence = {}
    for path, expected in STARTUP_PINS.items():
        try:
            raw = read(path)
        except (OSError, ValueError):
            continue
        if type(raw) is bytes and 0 < len(raw) <= MAX_BYTES and sha(raw) == expected:
            evidence[path] = raw
    startup = startup_facts(evidence.get(STARTUP, b""), evidence)
    categories = {row["kind"] for row in startup["startup_literal_reference_facts"]}
    main = config(evidence.get(MAIN, b""))
    includes = bool(main and main.get("include", "files", fallback="").split() in
                    [["conf.d/*.conf"], [INCLUDE + "/*.conf"]])
    holder = unit(evidence.get(HOLDER, b""), "nox-engram-cold-holder")
    model = unit(evidence.get(MODEL, b""), "nox-ds41-8098")
    dispatcher = unit(evidence.get(DISPATCHER, b""), DISPATCHER_SERVICE)
    holder_command_matches = (holder["command"] == ["/usr/bin/python3", "-I", "-B", HOLDER_SOURCE]
                              if holder else None)
    model_command_matches = model["command"] == ["/bin/bash", MODEL_GUARD] if model else None
    holder_auto = holder["autostart"] if holder else None
    model_auto = model["autostart"] if model else None
    holder_start_pinned = bool(holder_auto and holder_command_matches and HOLDER_SOURCE in evidence)
    model_start_pinned = bool(model_auto and model_command_matches
                              and MODEL_GUARD in evidence and MODEL_LAUNCHER in evidence)
    dispatcher_auto = dispatcher["autostart"] if dispatcher else None
    dispatcher_reference = "DISPATCHER_START_REFERENCE" in categories
    supervisor_reference = bool(categories & {"SUPERVISOR_STARTS_EXACT_MAIN", "SUPERVISOR_EXEC_EXACT_MAIN"})
    literal_configs_preserved = (STARTUP in evidence and includes and supervisor_reference
                                 and all(path in evidence for path in (HOLDER, MODEL, DISPATCHER))
                                 and not startup["supervisor_config_write_risk_count"]
                                 and not startup["supervisor_reference_unclassified_count"])
    return {**startup, "startup_pin_matches": STARTUP in evidence, "main_include_exact": includes,
            "holder_config_pinned": HOLDER in evidence, "model_config_pinned": MODEL in evidence,
            "dispatcher_config_pinned": DISPATCHER in evidence,
            "supervisor_launches_pinned_main_reference": supervisor_reference,
            "literal_config_references_preserve_pinned_units": literal_configs_preserved,
            "supervisor_exec_may_replace_onstart": "SUPERVISOR_EXEC_EXACT_MAIN" in categories,
            "holder_autostart_configured": holder_auto, "model_autostart_configured": model_auto,
            "holder_command_matches_expected": holder_command_matches,
            "model_command_matches_expected": model_command_matches,
            "holder_start_route_pinned": holder_start_pinned, "model_start_route_pinned": model_start_pinned,
            "holder_priority": holder["priority"] if holder else None,
            "model_priority": model["priority"] if model else None,
            "holder_precedes_model_by_priority": bool(
                holder_start_pinned and model_start_pinned and holder["priority"] < model["priority"]),
            "dispatcher_autostart_configured": dispatcher_auto,
            "dispatcher_onstart_reference": dispatcher_reference,
            "dispatcher_start_route_missing": dispatcher_auto is False and not dispatcher_reference,
            "protected_configs_live_verified_after_new_pid1": False, "server_rebooted": False}


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_pinned_root_file(path):
    """Read only the fixed regular root-owned files via anchored descriptors."""
    if path not in STARTUP_PINS:
        raise ValueError("PATH_NOT_ALLOWLISTED")
    parts = PurePosixPath(path).parts[1:]
    directory_open = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_open = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    with ExitStack() as stack:
        descriptor = os.open("/", directory_open)
        stack.callback(os.close, descriptor)
        for component in parts[:-1]:
            descriptor = os.open(component, directory_open, dir_fd=descriptor)
            stack.callback(os.close, descriptor)
            directory = os.fstat(descriptor)
            if directory.st_uid != 0 or directory.st_gid != 0 or directory.st_mode & 0o022:
                raise ValueError("UNTRUSTED_DIRECTORY")
        child = os.open(parts[-1], file_open, dir_fd=descriptor)
        with os.fdopen(child, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0
                    or before.st_mode & 0o022 or before.st_nlink != 1 or not 0 < before.st_size <= MAX_BYTES):
                raise ValueError("UNTRUSTED_FILE")
            raw = handle.read(MAX_BYTES + 1)
            after = os.fstat(handle.fileno())
            named = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if len(raw) != before.st_size or not file_identity(before) == file_identity(after) == file_identity(named):
                raise ValueError("CHANGED_FILE")
            return raw


def generation():
    with Path("/proc/1/stat").open("rb") as handle:
        raw = handle.read(8193)
    if len(raw) > 8192:
        raise ValueError("PID1_STAT_BOUND")
    return int(raw.rpartition(b") ")[2].split()[19])


def collect():
    files = {}

    def observe(path):
        try:
            raw = read_pinned_root_file(path)
        except FileNotFoundError:
            files[path] = {"state": "ABSENT"}
            raise
        except (OSError, ValueError):
            files[path] = {"state": "UNVERIFIED"}
            raise
        observed = sha(raw)
        files[path] = {"state": "MATCH" if observed == STARTUP_PINS[path] else "HASH_CHANGED",
                       "sha256": observed}
        return raw

    before = generation()
    facts = project(observe)
    stable = True
    for path, result in files.items():
        if result["state"] != "MATCH":
            continue
        try:
            stable &= sha(read_pinned_root_file(path)) == result["sha256"]
        except (OSError, ValueError):
            stable = False
    after = generation()
    if before != after or not stable:
        raise ValueError("CHANGED_STARTUP_EPOCH_OR_FILE")
    return {"authority": "READ_ONLY", "instance_id": 60509551,
            "pid1_start_ticks": before, "verified_file_pins": files,
            "host_writes": 0, "provider_mutations": 0, "service_signals": 0, **facts}


def boot_file_stamp(path):
    try:
        raw = read_pinned_root_file(path)
    except FileNotFoundError:
        return None
    info = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size != len(raw)):
        raise ValueError("UNTRUSTED_POSTIMAGE")
    return sha(raw), file_identity(info), bool(info.st_mode & 0o111)


def boot_postimage():
    epoch = generation()
    paths = STARTUP, BOOT_BACKUP
    before = tuple(boot_file_stamp(path) for path in paths)
    after = tuple(boot_file_stamp(path) for path in paths)
    if before != after or epoch != generation():
        raise ValueError("POSTIMAGE_CHANGED")
    startup, backup = before
    current_hash = startup[0] if startup is not None else None
    backup_hash = backup[0] if backup is not None else None
    original = STARTUP_PINS[STARTUP]
    blocker = None
    if current_hash == BOOT_CANDIDATE and backup_hash == original and startup[2] and backup[2]:
        decision = "PASS_DURABLE_HOOK_ON_DISK"
    elif current_hash == original and backup_hash is None:
        decision = "HOLD_ORIGINAL_STARTUP_UNCHANGED"
        if epoch != INSTALL_EPOCH:
            blocker = "INSTALL_GENERATION_DIFFERS_AT_READBACK"
        elif not startup[2]:
            blocker = "STARTUP_NOT_EXECUTABLE"
    elif current_hash == original and backup_hash == BOOT_CANDIDATE:
        decision = "HOLD_STAGED_CANDIDATE_UNEXCHANGED"
    else:
        decision = "HOLD_NONCANONICAL_STARTUP_PAIR"
    return {"decision": decision, "observed_blocker": blocker, "instance_id": 60509551,
            "pid1_start_ticks": epoch, "prior_cas_request_id": "7019378236",
            "onstart_sha256": current_hash, "backup_sha256": backup_hash,
            "onstart_executable": startup[2] if startup is not None else None,
            "prior_cas_epoch_matches": epoch == INSTALL_EPOCH,
            "authority": "READ_ONLY", "host_writes": 0, "service_operations": 0,
            "provider_mutations": 0, "cold_launch_verified": False}


def main():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    if not re.fullmatch(r"[1-9][0-9]*", request) or not re.fullmatch(r"[0-9a-f]{40}", source):
        raise SystemExit("HOLD_OWNER_CONTEXT")
    try:
        receipt = boot_postimage()
    except (OSError, ValueError, IndexError):
        receipt = {"decision": "HOLD_POSTIMAGE_UNAVAILABLE", "host_writes": 0,
                   "service_operations": 0, "provider_mutations": 0}
    print("NOX_MAINT_COLD_BOOT_RECEIPT=" + json.dumps(
        {**receipt, "request_id": request, "source_sha": source}, sort_keys=True), flush=True)
    print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)


if __name__ == "__main__":
    main()
