#!/usr/bin/env python3
"""Observe or advance one independently accepted window in the existing slot.

MODE is a reviewed source constant, never an untrusted task parameter.
OBSERVE writes no files. ADVANCE6 and ADVANCE1000 require terminal native
weight proof, an exact owned completion HOLD, immutable inputs, both existing
leases and a fresh owner request. This entry cannot retry a failed window.
"""
from __future__ import annotations

import base64
import configparser
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

MODE = "ADVANCE6"  # Reviewed transition after native first-five observation.
INITIAL_REQUEST = "6907283384"
INITIAL_SOURCE = "2a0d18d8c4434c4798335868df4b28be0e507ed5"
HELPER_NAME = "owner_qwen_install_entry.py"
HELPER_SHA = "864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7"
CHECKPOINT = re.compile(r"checkpoint-u\d{8}-a\d{8}-g\d{20}")
SHA = re.compile(r"[a-f0-9]{64}")
ID = re.compile(r"\d{1,24}")
_HELPER = None


def fail(code):
    raise RuntimeError(code)


def helper():
    global _HELPER
    if _HELPER is None:
        raw = base64.b64decode(BUNDLE.get(HELPER_NAME, ""), validate=True)
        if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
            fail("HOLD_QWEN_WINDOW_HELPER_PIN")
        value = types.ModuleType("_nox_qwen_pinned_install_helper")
        value.__file__ = "/root/nox/scripts/" + HELPER_NAME
        # Split the token: the native operator globally materializes its one
        # top-level placeholder before this code is compiled.
        value.__dict__["__NOX_" + "BUNDLE_JSON__"] = BUNDLE
        exec(compile(raw, value.__file__, "exec"), value.__dict__)
        _HELPER = value
    return _HELPER


def document(h, path, maximum=2 * 1024 ** 2):
    raw = h.read(path, maximum)
    value = json.loads(raw)
    if not isinstance(value, dict):
        fail("HOLD_QWEN_WINDOW_JSON_OBJECT")
    return value, raw


def source_contract(h):
    verified = {}
    for name, expected in h.PINS.items():
        raw = h.read(h.SCRIPTS / name)
        if h.digest(raw) != expected:
            fail("HOLD_QWEN_WINDOW_INSTALLED_SOURCE_DRIFT")
        verified[name] = raw
    if h.digest(h.read(h.SUPERVISOR)) != h.SUPERVISOR_SHA:
        fail("HOLD_QWEN_WINDOW_SUPERVISOR_DRIFT")
    raw = verified["owner_qwen_training_contract.py"]
    value = types.ModuleType("_nox_qwen_window_contract")
    value.__file__ = str(h.SCRIPTS / "owner_qwen_training_contract.py")
    exec(compile(raw, value.__file__, "exec"), value.__dict__)
    return value


def arguments(h, profile, request, admission_sha, goal, *, resume):
    corpus = h.STATE / "qwen_corpus" / INITIAL_REQUEST
    result = ["/root/venv_volta/bin/python", "-u", str(h.SCRIPTS / "qwen_student_training_entry.py"),
              "--request", request, "--admission-sha256", admission_sha,
              "--base-directory", profile["base_directory"], "--base-transport", "sealed-memfd",
              "--manifest", str(h.SCRIPTS / "qwen35_9b_manifest.json"),
              "--output-directory", profile["output_directory"],
              "--train-jsonl", str(corpus / "train.jsonl"), "--train-sha256", profile["train_sha256"],
              "--holdout-jsonl", str(corpus / "holdout.jsonl"), "--holdout-sha256", profile["holdout_sha256"],
              "--dataset-manifest", str(corpus / "corpus_manifest.json"),
              "--dataset-manifest-sha256", profile["dataset_manifest_sha256"],
              "--successful-updates", str(goal)]
    if resume:
        result.append("--resume")
    return result


def wrapper(h, args, request, goal):
    if goal not in (5, 6, 1000) or not ID.fullmatch(request):
        fail("HOLD_QWEN_WINDOW_WRAPPER_SCOPE")
    raw = h.wrapper(args, request)
    anchor = br" goal=5\n"
    if raw.count(anchor) != 1:
        fail("HOLD_QWEN_WINDOW_PINNED_WRAPPER_ANCHOR")
    # The complete template comes from HELPER_SHA. Only its reviewed numeric
    # completion label changes; its STOP checks, child trap and O_EXCL remain.
    return raw.replace(anchor, (" goal=" + str(goal) + "\\n").encode(), 1)


def context(h):
    admission, raw = document(h, h.ADMISSION, 64000)
    p = admission.get("student_profile", {})
    expected_sources = {str(h.SCRIPTS / n): s for n, s in h.PINS.items() if n.endswith(".py")}
    if (admission.get("schema") != "NOX_OWNER_TRAINING_ADMISSION_V1"
            or admission.get("initial_request") != INITIAL_REQUEST
            or not ID.fullmatch(str(admission.get("request", "")))
            or admission.get("sources") != expected_sources
            or p.get("schema") != "NOX_QWEN35_9B_SINGLE_TRAINER_V1"
            or p.get("output_directory") != str(h.ROOT / "lora/qwen35_9b" / INITIAL_REQUEST)
            or p.get("base_directory") != str(h.STATE / "qwen_memfd")
            or p.get("base_transport") != "sealed-memfd"
            or p.get("physical_gpu") != 1 or p.get("training_service") != h.SERVICE
            or p.get("successful_updates_goal") not in (5, 6, 1000)):
        fail("HOLD_QWEN_ACTIVE_ADMISSION_IDENTITY")
    c = source_contract(h)
    if (p.get("model_id") != c.MODEL_ID or p.get("revision") != c.REVISION
            or p.get("base_manifest_sha256") != c.MANIFEST_SHA):
        fail("HOLD_QWEN_WINDOW_BASE_IDENTITY")
    initial, _ = document(h, h.STATE / ("owner_qwen_install_" + INITIAL_REQUEST + ".json"))
    if (initial.get("schema") != "NOX_QWEN_INITIAL_OWNER_INSTALL_V1"
            or initial.get("request") != INITIAL_REQUEST or initial.get("source_sha") != INITIAL_SOURCE
            or initial.get("state") != "NEW_STUDENT_STARTED_ACCEPTANCE_PENDING"
            or initial.get("source_pins") != h.PINS):
        fail("HOLD_QWEN_INITIAL_INSTALL_RECEIPT")
    original = initial.get("student_profile", {})
    immutable = ("schema", "model_id", "revision", "base_manifest_sha256", "base_directory", "base_transport",
                 "output_directory", "train_sha256", "holdout_sha256", "dataset_manifest_sha256",
                 "physical_gpu", "training_service", "runtime_versions")
    if any(p.get(k) != original.get(k) for k in immutable):
        fail("HOLD_QWEN_WINDOW_IMMUTABLE_PROFILE_DRIFT")
    goal = p["successful_updates_goal"]
    if goal == 5:
        if (admission.get("request") != INITIAL_REQUEST or admission.get("source_sha") != INITIAL_SOURCE
                or h.digest(raw) != initial.get("admission_sha256")):
            fail("HOLD_QWEN_INITIAL_ADMISSION_SHA")
    else:
        previous, _ = document(h, h.STATE / ("owner_qwen_window_" + admission["request"] + ".json"))
        if (previous.get("schema") != "NOX_QWEN_WINDOW_ADVANCE_V1"
                or previous.get("request") != admission["request"]
                or previous.get("state") != "WINDOW_STARTED_ACCEPTANCE_PENDING"
                or previous.get("target_goal") != goal
                or previous.get("source_sha") != admission.get("source_sha")
                or previous.get("new_admission_sha256") != h.digest(raw)):
            fail("HOLD_QWEN_PREVIOUS_WINDOW_RECEIPT")
    expected_wrapper = wrapper(h, arguments(h, p, admission["request"], h.digest(raw), goal,
                                           resume=goal != 5), admission["request"], goal)
    actual_wrapper = h.read(h.WRAPPER)
    if actual_wrapper != expected_wrapper:
        fail("HOLD_QWEN_ACTIVE_WRAPPER_BYTES")
    corpus = h.STATE / "qwen_corpus" / INITIAL_REQUEST
    for name, key in (("train.jsonl", "train_sha256"), ("holdout.jsonl", "holdout_sha256"),
                      ("corpus_manifest.json", "dataset_manifest_sha256")):
        if c.sha256_file(corpus / name) != p[key]:
            fail("HOLD_QWEN_WINDOW_CORPUS_SNAPSHOT_DRIFT")
    corpus_receipt, _ = document(h, corpus / "corpus_manifest.json")
    if (corpus_receipt.get("schema") != "NOX_QWEN35_CORPUS_SNAPSHOT_V1"
            or corpus_receipt.get("train_sha256") != p["train_sha256"]
            or corpus_receipt.get("holdout_sha256") != p["holdout_sha256"]
            or corpus_receipt.get("source_loader_sha256") != h.NATIVE_TRAINER_SHA
            or corpus_receipt.get("group_disjoint") is not True):
        fail("HOLD_QWEN_WINDOW_CORPUS_PROVENANCE")
    return {"admission": admission, "raw": raw, "profile": p, "contract": c,
            "wrapper": actual_wrapper, "output": h.ROOT / "lora/qwen35_9b" / INITIAL_REQUEST,
            "corpus": corpus_receipt}


def process_info(pid):
    if type(pid) is not int or pid <= 0:
        return None
    folder = Path("/proc") / str(pid)
    try:
        fields = (folder / "stat").read_text().rsplit(") ", 1)[1].split()
        return {"pid": pid, "start_ticks": int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def process_chain(h, supervisor_pid):
    if process_info(supervisor_pid) is None:
        return {"processes": [], "gpu_release_verified": False}
    pending = [(supervisor_pid, None)]; records = []; visited = set()
    while pending and len(visited) < 16:
        pid, parent = pending.pop(0)
        if pid in visited:
            continue
        visited.add(pid); before = process_info(pid)
        if before is None:
            continue
        folder = Path("/proc") / str(pid)
        try:
            with (folder / "cmdline").open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                continue
            args = raw.split(b"\0")
            kind = ("qwen_student" if str(h.SCRIPTS / "qwen_student_training_entry.py").encode() in args
                    else "supervisor_wrapper" if str(h.WRAPPER).encode() in args else "other_child")
            row = {**before, "parent_pid": parent, "command_kind": kind}
            if kind == "qwen_student":
                count = total = 0
                with os.scandir(folder / "fd") as descriptors:
                    for i, fd in enumerate(descriptors):
                        if i >= 512:
                            row["descriptor_scan_truncated"] = True; break
                        try:
                            target = os.readlink(fd.path)
                            if target.startswith("/memfd:nox-qwen-"):
                                count += 1; total += os.stat(fd.path).st_size
                        except (OSError, ValueError):
                            continue
                row.update(memfd_file_count=count, memfd_bytes_observed=total,
                           weights_sha_verified_from_fd_metadata=False)
            children_raw = (folder / "task" / str(pid) / "children").read_text()
            if len(children_raw) <= 4096:
                pending.extend((int(x), pid) for x in children_raw.split()[:16] if x.isdigit())
            if process_info(pid) == before:
                records.append(row)
        except (OSError, ValueError, IndexError):
            continue
    return {"processes": records, "gpu_release_verified": False}


def safe_log_summary(raw):
    """Return identifiers and counts only. Never return an exception message."""
    codes = []; exceptions = []; events = []
    safe_states = {"PINNED_PUBLIC_BASE_STAGING", "REAL_CORPUS_TOKENIZED_ADMISSION",
                   "STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED",
                   "STUDENT_RESTART_AND_UPDATES_VERIFIED"}
    safe_exceptions = {"RuntimeError", "ValueError", "TypeError", "ImportError", "ModuleNotFoundError",
                       "KeyError", "IndexError", "AttributeError", "AssertionError", "OSError", "FileNotFoundError",
                       "PermissionError", "TimeoutError", "MemoryError", "OutOfMemoryError", "UnicodeDecodeError",
                       "JSONDecodeError", "HTTPError", "URLError", "SafetensorError", "TemplateError",
                       "TemplateRuntimeError", "AcceleratorError", "Hold"}
    for line in raw.decode("utf8", "replace").splitlines():
        if len(line) > 32768:
            continue
        # Only a Python exception TYPE at line start, never its path/message.
        match = re.match(r"^(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*(?:Error|Exception)|Hold):(?: |$)", line)
        if match and match[1] in safe_exceptions:
            exceptions.append(match[1])
            suffix = line[match.end():].strip()
            if re.fullmatch(r"HOLD_[A-Z0-9_]{1,120}", suffix):
                codes.append(suffix)
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        state = value.get("state")
        if isinstance(state, str) and re.fullmatch(r"HOLD_[A-Z0-9_]{1,120}", state):
            codes.append(state); events.append({"state": state})
        elif isinstance(state, str) and state in safe_states:
            event = {"state": state}
            if state == "PINNED_PUBLIC_BASE_STAGING":
                # Only counts; a filename supplied by a log line is not echoed.
                if (type(value.get("bytes")) is int and type(value.get("total")) is int
                        and 0 <= value["bytes"] <= value["total"] <= 20 * 1024 ** 3):
                    event.update(public_file_bytes=value["bytes"], public_file_total_bytes=value["total"])
            events.append(event)
    return {"hold_codes": list(dict.fromkeys(codes))[-8:],
            "exception_types": list(dict.fromkeys(exceptions))[-8:], "safe_events": events[-4:],
            "may_include_prior_runs": True, "raw_text_exported": False}


def log_diagnostics(h):
    raw_config = h.read(h.SUPERVISOR)
    if h.digest(raw_config) != h.SUPERVISOR_SHA:
        fail("HOLD_QWEN_DIAGNOSTIC_SUPERVISOR_PIN")
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(raw_config.decode())
    section = "program:" + h.SERVICE
    output = []
    for stream in ("stdout", "stderr"):
        name = config.get(section, stream + "_logfile", fallback="")
        if not name or name.upper() in {"AUTO", "NONE"}:
            output.append({"stream": stream, "status": "NO_EXPLICIT_PINNED_LOG_PATH"}); continue
        path = Path(name)
        if (not path.is_absolute() or path.resolve() != path
                or not path.is_relative_to(h.ROOT / "logs")):
            output.append({"stream": stream, "status": "LOG_PATH_OUTSIDE_EXPLICIT_SCOPE"}); continue
        try:
            fd = os.open(h.plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    fail("HOLD_QWEN_DIAGNOSTIC_LOG_TYPE")
                handle.seek(max(0, info.st_size - 65536))
                data = handle.read(65536)
            output.append({"stream": stream, "log_bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                           "tail_bytes_read": len(data), **safe_log_summary(data)})
        except FileNotFoundError:
            output.append({"stream": stream, "status": "PINNED_LOG_NOT_PRESENT"})
    return output


def observe(h):
    ctx = context(h); p = ctx["profile"]; output = ctx["output"]
    service = h.service()
    result = {"schema": "NOX_QWEN_WINDOW_OBSERVATION_V1", "state": "OBSERVED_NOT_ADVANCED",
              "time": time.time(), "initial_request": INITIAL_REQUEST,
              "active_request": ctx["admission"]["request"], "active_goal": p["successful_updates_goal"],
              "admission_sha256": h.digest(ctx["raw"]), "model_id": p["model_id"], "revision": p["revision"],
              "service": service, "supervisor_process": process_info(service.get("pid")),
              "manual_stop_or_pause": h.owner_stop(), "content_exported": False, "files_written": 0}
    result["process_chain"] = process_chain(h, service.get("pid"))
    result["log_diagnostics"] = log_diagnostics(h)
    for name, label in (("owner_progress.json", "progress"), ("owner_last_result.json", "final_result")):
        path = output / name
        if not path.exists():
            result[label] = {"present": False}; continue
        value, raw = document(h, path)
        keys = ("state", "successful_optimizer_steps", "new_successful_optimizer_steps", "attempted_steps",
                "skipped_steps", "adapter_tensor_sha256", "final_adapter_tensor_sha256", "reload_verified",
                "independent_holdout_accepted", "holdout_evaluated_successful_total", "pid", "time", "process_identity")
        result[label] = {"present": True, "file_sha256": h.digest(raw),
                         **{k: value[k] for k in keys if k in value}}
        if label == "final_result":
            result[label]["matches_current_goal"] = value.get("successful_optimizer_steps") == p["successful_updates_goal"]
    pointer = output / "latest_checkpoint.json"
    if pointer.exists():
        latest, before = document(h, pointer, 16000)
        name = latest.get("directory", "")
        if not CHECKPOINT.fullmatch(name):
            fail("HOLD_QWEN_OBSERVE_CHECKPOINT_SCOPE")
        checkpoint, raw = document(h, output / name / "checkpoint_manifest.json", 64000)
        result["checkpoint"] = {"directory": name, "manifest_sha256": h.digest(raw),
            "manifest_sha256_verified": h.digest(raw) == latest.get("manifest_sha256"),
            "successful_total": checkpoint.get("successful_total"),
            "weight_hashes": "RECORDED_NOT_REHASHED_IN_OBSERVE",
            "recorded_file_count": len(checkpoint.get("files_sha256", {})),
            "pointer_stable": h.read(pointer, 16000) == before}
    result["admission_stable"] = h.read(h.ADMISSION, 64000) == ctx["raw"]
    if h.HOLD.exists() or h.HOLD.is_symlink():
        raw = h.read(h.HOLD, 256)
        expected = completion_hold(ctx["admission"]["request"], p["successful_updates_goal"])
        result["hold"] = {"bytes": len(raw), "sha256": h.digest(raw), "matches_owned_completion": raw == expected}
    return result


def completion_hold(request, goal):
    if not ID.fullmatch(str(request)) or goal not in (5, 6, 1000):
        fail("HOLD_QWEN_COMPLETION_CONTEXT")
    return (f"OWNER_QWEN_WINDOW_COMPLETE request={request} goal={goal}\n").encode()


def validate_terminal(ctx, lineage, receipt, goal):
    c = ctx["contract"]; p = ctx["profile"]
    if (lineage.get("schema") != c.SCHEMA or lineage.get("base", {}).get("model_id") != c.MODEL_ID
            or lineage.get("base", {}).get("revision") != c.REVISION
            or lineage.get("base", {}).get("manifest_sha256") != c.MANIFEST_SHA
            or lineage.get("base", {}).get("full_base_sha256_verified") is not True
            or lineage.get("target_names") != list(c.text_projection_names())
            or lineage.get("train_sha256") != p["train_sha256"]
            or lineage.get("holdout_sha256") != p["holdout_sha256"]
            or lineage.get("dataset_manifest_sha256") != p["dataset_manifest_sha256"]
            or lineage.get("runtime_versions") != p["runtime_versions"]
            or lineage.get("precision") != "NF4_FP16_FP32_LORA"):
        fail("HOLD_QWEN_TERMINAL_LINEAGE")
    if (receipt.get("schema") != c.PROOF_SCHEMA or receipt.get("lineage_sha256") != c.canonical_sha(lineage)
            or receipt.get("base_manifest_sha256") != c.MANIFEST_SHA
            or receipt.get("successful_optimizer_steps") != goal
            or receipt.get("holdout_evaluated_successful_total") != goal
            or receipt.get("holdout_finite") is not True
            or receipt.get("independent_holdout_accepted") is not True
            or receipt.get("old_optimizer_loaded") is not False):
        fail("HOLD_QWEN_TERMINAL_ACCEPTANCE")
    updates = receipt.get("update_evidence")
    if not isinstance(updates, list) or len(updates) != goal:
        fail("HOLD_QWEN_TERMINAL_UPDATE_COUNT")
    previous = None
    for row in updates:
        c.validate_update_evidence(row)
        if previous and (row["optimizer_step_before"] != previous["optimizer_step_after"]
                         or row["adapter_sha_before"] != previous["adapter_sha_after"]):
            fail("HOLD_QWEN_TERMINAL_UPDATE_CHAIN")
        previous = row
    if (updates[0]["optimizer_step_before"] != 0 or updates[-1]["optimizer_step_after"] != goal
            or updates[-1]["adapter_sha_after"] != receipt.get("final_adapter_tensor_sha256")
            or len({v for r in updates[:5] for v in r["training_example_sha256"]}) != 40):
        fail("HOLD_QWEN_TERMINAL_REAL_UPDATE_EVIDENCE")
    if goal == 5:
        if (receipt.get("state") != "STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED"
                or receipt.get("reload_verified") is not False
                or receipt.get("new_successful_optimizer_steps") != 5):
            fail("HOLD_QWEN_INITIAL_FIVE_NOT_ACCEPTED")
    elif goal == 6:
        if (receipt.get("state") != "STUDENT_RESTART_AND_UPDATES_VERIFIED"
                or receipt.get("new_successful_optimizer_steps") != 1):
            fail("HOLD_QWEN_RELOAD_SIX_NOT_ACCEPTED")
        c.verify_proof(receipt, lineage=lineage, minimum_updates=6)
    else:
        fail("HOLD_QWEN_ADVANCE_PREVIOUS_GOAL")


def stream_sha(h, path, expected, *, deadline, budget):
    path = h.plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest = hashlib.sha256()
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 2 * 1024 ** 3:
            fail("HOLD_QWEN_CHECKPOINT_FILE_SCOPE")
        budget[0] += before.st_size
        if budget[0] > 2 * 1024 ** 3:
            fail("HOLD_QWEN_CHECKPOINT_TOTAL_BYTE_BOUND")
        while True:
            if h.owner_stop() or time.monotonic() > deadline:
                fail("HOLD_QWEN_STOP_OR_CHECKPOINT_VERIFY_TIME_BOUND")
            block = stream.read(1024 ** 2)
            if not block:
                break
            digest.update(block)
        after = os.fstat(stream.fileno())
    named = path.stat()
    identities = [(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) for s in (before, after, named)]
    if len(set(identities)) != 1 or digest.hexdigest() != expected:
        fail("HOLD_QWEN_CHECKPOINT_FILE_CHANGED")
    return before.st_size


def verify_checkpoint(h, ctx, receipt, lineage):
    output = ctx["output"]
    latest, latest_raw = document(h, output / "latest_checkpoint.json", 16000)
    name = latest.get("directory", "")
    if not CHECKPOINT.fullmatch(name) or receipt.get("checkpoint") != str(output / name):
        fail("HOLD_QWEN_TERMINAL_CHECKPOINT_SCOPE")
    record, raw = document(h, output / name / "checkpoint_manifest.json", 64000)
    if (h.digest(raw) != latest.get("manifest_sha256")
            or h.digest(raw) != receipt.get("checkpoint_manifest_sha256")
            or record.get("schema") != "NOX_QWEN35_9B_CHECKPOINT_V1"
            or record.get("directory") != name
            or record.get("lineage_sha256") != ctx["contract"].canonical_sha(lineage)
            or record.get("successful_total") != receipt["successful_optimizer_steps"]
            or record.get("adapter_tensor_sha256") != receipt["final_adapter_tensor_sha256"]):
        fail("HOLD_QWEN_TERMINAL_CHECKPOINT_MANIFEST")
    files = record.get("files_sha256", {})
    required = {"adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "scheduler.pt",
                "scaler.pt", "rng_state.pt", "python_rng.json", "student_state.json", "lineage.json"}
    if (not isinstance(files, dict) or not required <= set(files) or len(files) > 32
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", n) or n in (".", "..")
                   or not isinstance(v, str) or not SHA.fullmatch(v) for n, v in files.items())
            or {p.name for p in (output / name).iterdir()} != set(files) | {"checkpoint_manifest.json"}):
        fail("HOLD_QWEN_TERMINAL_CHECKPOINT_FILE_SET")
    budget = [0]; deadline = time.monotonic() + 90
    for filename, expected in files.items():
        stream_sha(h, output / name / filename, expected, deadline=deadline, budget=budget)
    saved_lineage, _ = document(h, output / name / "lineage.json")
    state, _ = document(h, output / name / "student_state.json")
    if (saved_lineage != lineage or state.get("successful_total") != receipt["successful_optimizer_steps"]
            or state.get("update_evidence") != receipt["update_evidence"]
            or h.read(output / "latest_checkpoint.json", 16000) != latest_raw):
        fail("HOLD_QWEN_TERMINAL_CHECKPOINT_STATE")
    return {"directory": name, "manifest_sha256": h.digest(raw), "verified_files": len(files),
            "verified_bytes": budget[0], "all_checkpoint_file_sha256_verified": True}


def validate_advance(h, ctx, target):
    expected = {6: 5, 1000: 6}.get(target)
    if expected is None or ctx["profile"]["successful_updates_goal"] != expected:
        fail("HOLD_QWEN_NEXT_WINDOW_PHASE")
    if h.owner_stop() or h.service()["state"] not in ("STOPPED", "FATAL", "EXITED"):
        fail("HOLD_QWEN_WINDOW_STOP_OR_ACTIVE_TRAINER")
    hold = completion_hold(ctx["admission"]["request"], expected)
    if h.read(h.HOLD, 256) != hold:
        fail("HOLD_QWEN_OWNED_COMPLETE_FLAG_REQUIRED")
    policy, _ = document(h, h.STATE / "task_boost_mode.json", 16000)
    if (policy.get("enabled") is not True or policy.get("mode") != "TASK_BOOST"
            or policy.get("training_allowed") is not True or policy.get("training_gpu") != 1
            or policy.get("training_service") != h.SERVICE):
        fail("HOLD_QWEN_WINDOW_TRAINING_POLICY")
    lineage, _ = document(h, ctx["output"] / "owner_lineage.json")
    receipt, receipt_raw = document(h, ctx["output"] / "owner_last_result.json")
    validate_terminal(ctx, lineage, receipt, expected)
    for key, name in (("entry_sha256", "qwen_student_training_entry.py"),
                      ("contract_sha256", "owner_qwen_training_contract.py"),
                      ("memfd_source_sha256", "owner_qwen_memfd.py")):
        if lineage.get(key) != h.PINS[name]:
            fail("HOLD_QWEN_WINDOW_LINEAGE_SOURCE_DRIFT")
    checkpoint = verify_checkpoint(h, ctx, receipt, lineage)
    certificate_sha = None
    if target == 1000:
        certificate, raw = document(h, ctx["output"] / "owner_acceptance.json")
        ctx["contract"].verify_proof(certificate, lineage=lineage, minimum_updates=6)
        if certificate != receipt:
            fail("HOLD_QWEN_IMMUTABLE_SIX_ACCEPTANCE_MISMATCH")
        certificate_sha = h.digest(raw)
    return {"previous_goal": expected, "target_goal": target, "hold": hold,
            "terminal_receipt_sha256": h.digest(receipt_raw), "checkpoint": checkpoint,
            "acceptance_sha256": certificate_sha, "lineage_sha256": ctx["contract"].canonical_sha(lineage)}


def latch_failure(h, request):
    try:
        fd = os.open(h.HOLD, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return "EXISTING_FLAG_PRESERVED"
    with os.fdopen(fd, "w") as stream:
        stream.write("OWNER_QWEN_WINDOW_ADVANCE_FAILED request=" + request + "\n")
        stream.flush(); os.fsync(stream.fileno())
    return "OWNED_FAILURE_FLAG_CREATED"


def rename_noreplace(source, destination):
    """Linux atomic no-clobber rename. Fail closed where it is unavailable."""
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        fail("HOLD_QWEN_ATOMIC_NOREPLACE_UNAVAILABLE")
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        if number == errno.EEXIST:
            raise FileExistsError(number, "destination already exists")
        if number in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            fail("HOLD_QWEN_ATOMIC_NOREPLACE_UNAVAILABLE")
        raise OSError(number, "atomic flag move failed")


def restore_hold_noclobber(h, saved):
    # Do not call plain(saved): an unexpected owner symlink must itself be
    # restored, not followed or rejected after we have preserved it.
    h.plain(Path(saved).parent); h.plain(h.HOLD.parent)
    mode = os.lstat(saved).st_mode
    try:
        if stat.S_ISDIR(mode):
            rename_noreplace(saved, h.HOLD)
            return "RESTORED_DIRECTORY_WITHOUT_CLOBBER"
        os.link(saved, h.HOLD, follow_symlinks=False)
        return "RESTORED_SAME_FLAG_INODE_ARCHIVE_RETAINED"
    except FileExistsError:
        return "NEW_FLAG_PRESERVED_SAVED_FLAG_RETAINED"


def archive_completed_hold(h, archive, expected):
    h.plain(archive.parent)
    if h.read(h.HOLD, 256) != expected:
        fail("HOLD_QWEN_COMPLETION_CHANGED_BEFORE_ARCHIVE")
    rename_noreplace(h.HOLD, archive)
    try:
        if h.read(archive, 256) == expected:
            return {"expected_flag": True}
    except (OSError, RuntimeError):
        pass
    # A user may replace HOLD between our check and rename. The moved inode
    # survives in archive and is restored without overwriting a newer flag.
    return {"expected_flag": False, "preserved_archive": str(archive),
            "restoration": restore_hold_noclobber(h, archive)}


def advance(h, target, request, source):
    if not ID.fullmatch(request) or not re.fullmatch(r"[a-f0-9]{40}", source):
        fail("HOLD_QWEN_WINDOW_OWNER_CONTEXT")
    receipt_path = h.STATE / ("owner_qwen_window_" + request + ".json")
    backup = h.ROOT / "backup/owner_qwen_window" / request
    for path in (receipt_path, backup):
        h.plain(path)
        if path.exists() or path.is_symlink():
            fail("HOLD_QWEN_WINDOW_REQUEST_ALREADY_USED")
    maintenance = os.open(h.plain(h.STATE / "owner_maintenance.lock"), os.O_RDWR | os.O_NOFOLLOW)
    training = None; flag_owned = False; released = False
    note = ("NOX_QWEN_WINDOW_ADVANCE " + request + " " + source + "\n").encode()
    flag = h.STATE / "OWNER_MAINTENANCE.flag"
    result = {"schema": "NOX_QWEN_WINDOW_ADVANCE_V1", "request": request, "source_sha": source,
              "initial_request": INITIAL_REQUEST, "target_goal": target, "started_at": time.time(),
              "state": "PREFLIGHT", "main_chat_changed": False, "manual_stop_cleared": False,
              "new_service_created": False, "checkpoint_or_corpus_deleted": False}
    ctx = None; archived = False; new_raw = None; new_wrapper = None
    try:
        fcntl.flock(maintenance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        training = os.open(h.plain(h.STATE / "forge_training.lock"), os.O_RDWR | os.O_NOFOLLOW)
        fcntl.flock(training, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if flag.exists() or flag.is_symlink():
            fail("HOLD_QWEN_EXISTING_OWNER_MAINTENANCE")
        ctx = context(h)
        if request == ctx["admission"]["request"]:
            fail("HOLD_QWEN_NEW_REQUEST_REQUIRED")
        evidence = validate_advance(h, ctx, target)
        before_model = h.model_identity()
        resources = h.resource_check()
        fd = os.open(h.plain(flag), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(note); stream.flush(); os.fsync(stream.fileno())
        flag_owned = True
        h.atomic(receipt_path, h.encode(result))
        h.atomic(backup / "previous_admission.json", ctx["raw"])
        h.atomic(backup / "previous_wrapper.sh", ctx["wrapper"])
        value = dict(ctx["admission"])
        profile = dict(ctx["profile"]); profile["successful_updates_goal"] = target
        value.update(request=request, source_sha=source, student_profile=profile, created_at=time.time(),
                     previous_request=ctx["admission"]["request"],
                     previous_admission_sha256=h.digest(ctx["raw"]),
                     accepted_previous_window=evidence["terminal_receipt_sha256"])
        new_raw = h.encode(value)
        new_wrapper = wrapper(h, arguments(h, profile, request, h.digest(new_raw), target, resume=True), request, target)
        subprocess.run(["bash", "-n"], input=new_wrapper, capture_output=True, check=True, timeout=5)
        fresh = context(h)
        if (fresh["raw"] != ctx["raw"] or fresh["wrapper"] != ctx["wrapper"]
                or h.read(flag, 256) != note or h.owner_stop()
                or h.read(h.HOLD, 256) != evidence["hold"]
                or h.service()["state"] not in ("STOPPED", "FATAL", "EXITED")
                or h.model_identity() != before_model):
            fail("HOLD_QWEN_WINDOW_HANDOFF_CHANGED")
        h.resource_check()
        h.atomic(h.ADMISSION, new_raw)
        h.atomic(h.WRAPPER, new_wrapper, mode=0o700)
        if h.read(h.ADMISSION, 64000) != new_raw or h.read(h.WRAPPER) != new_wrapper:
            fail("HOLD_QWEN_NEW_WINDOW_SOURCE_READBACK")
        archive = backup / "previous_complete_HOLD.flag"
        if archive.exists() or archive.is_symlink() or h.read(h.HOLD, 256) != evidence["hold"] or h.owner_stop():
            fail("HOLD_QWEN_COMPLETION_ARCHIVE_RACE")
        moved = archive_completed_hold(h, archive, evidence["hold"])
        if not moved["expected_flag"]:
            result["unexpected_hold_preserved"] = moved
            fail("HOLD_QWEN_OWNER_FLAG_REPLACED_DURING_ARCHIVE")
        archived = True
        result.update(state="PREVIOUS_WINDOW_ACCEPTED_NEW_WINDOW_INSTALLED", previous_request=ctx["admission"]["request"],
                      previous_admission_sha256=h.digest(ctx["raw"]), new_admission_sha256=h.digest(new_raw),
                      wrapper_sha256=h.digest(new_wrapper), acceptance={k: v for k, v in evidence.items() if k != "hold"},
                      initial_resources=resources, active_chat_before=before_model, output_directory=str(ctx["output"]))
        h.atomic(receipt_path, h.encode(result))
        if h.owner_stop() or h.HOLD.exists() or h.HOLD.is_symlink():
            fail("HOLD_QWEN_OWNER_STOP_BEFORE_START")
        os.close(training); training = None; released = True
        started = h.command(["supervisorctl", "start", h.SERVICE], 30)
        observed = h.service()
        if started.returncode != 0 or observed["state"] != "RUNNING" or not observed.get("pid"):
            fail("HOLD_QWEN_NEW_WINDOW_START_UNVERIFIED")
        if h.model_identity() != before_model:
            fail("HOLD_QWEN_CHAT_IDENTITY_CHANGED")
        result.update(state="WINDOW_STARTED_ACCEPTANCE_PENDING", service_after=observed,
                      active_chat_after=before_model, requested_window_complete=False,
                      new_optimizer_updates_verified=False)
    except Exception as exc:
        message = str(exc)
        result.update(state="HOLD", error=message if re.fullmatch(r"HOLD_[A-Z0-9_]+", message) else type(exc).__name__)
        if released:
            result["failure_hold"] = latch_failure(h, request)
            try:
                result["service_after_failure"] = h.service()
            except Exception:
                result["service_after_failure"] = {"state": "UNKNOWN"}
            result.update(shutdown_pending_or_unverified=True, gpu_memory_released_verified=False)
        elif ctx is not None and flag_owned:
            try:
                if new_wrapper is not None and h.read(h.WRAPPER) == new_wrapper:
                    h.atomic(h.WRAPPER, ctx["wrapper"], mode=0o700)
                if new_raw is not None and h.read(h.ADMISSION, 64000) == new_raw:
                    h.atomic(h.ADMISSION, ctx["raw"])
                if archived:
                    saved_hold = backup / "previous_complete_HOLD.flag"
                    if h.read(saved_hold, 256) != evidence["hold"]:
                        fail("HOLD_QWEN_ROLLBACK_ARCHIVE_CHANGED")
                    result["rollback_hold_restoration"] = restore_hold_noclobber(h, saved_hold)
                result["prestart_rollback_completed"] = (
                    h.read(h.WRAPPER) == ctx["wrapper"] and h.read(h.ADMISSION, 64000) == ctx["raw"])
            except Exception as rollback:
                result["rollback_error"] = type(rollback).__name__
    finally:
        if training is not None:
            os.close(training)
        if flag_owned and flag.exists() and h.read(flag, 256) == note:
            flag.unlink()
        os.close(maintenance)
    result["finished_at"] = time.time()
    if flag_owned:
        h.atomic(receipt_path, h.encode(result))
    return result


def main():
    h = helper()
    if MODE == "OBSERVE":
        result = observe(h)
    elif MODE in ("ADVANCE6", "ADVANCE1000"):
        result = advance(h, 6 if MODE == "ADVANCE6" else 1000,
                         os.environ.get("NOX_OWNER_REQUEST_ID", ""), os.environ.get("NOX_OWNER_SOURCE_SHA", ""))
    else:
        fail("HOLD_UNREVIEWED_QWEN_WINDOW_MODE")
    print("NOX_MAINT_REPAIR=" + json.dumps({"kind": "qwen_window", "data": result}, sort_keys=True), flush=True)
    ok = result["state"] in ("OBSERVED_NOT_ADVANCED", "WINDOW_STARTED_ACCEPTANCE_PENDING")
    print("NOX_MAINT_REPAIR_COMPLETE=" + str(ok).lower(), flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = str(exc)
        code = message if re.fullmatch(r"HOLD_[A-Z0-9_]+", message) else "HOLD_" + type(exc).__name__.upper()
        print("NOX_MAINT_REPAIR=" + json.dumps({"kind": "qwen_window", "state": code}), flush=True)
        print("NOX_MAINT_REPAIR_COMPLETE=false", flush=True)
        raise SystemExit(2)
