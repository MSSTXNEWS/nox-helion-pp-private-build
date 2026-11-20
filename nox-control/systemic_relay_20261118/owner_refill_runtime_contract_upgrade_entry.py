#!/usr/bin/env python3
"""One-shot, owner-pinned upgrade of the existing native REFILL selector only.

Reuses the one dispatcher, its three workers and the same durable queue. No
new scheduler, task, original acceptance, model, S03, or workspace mutation.
On unexpected live state: HOLD before stopping; on boot failure: verified
preimage recovery under the existing owner maintenance lock.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import types

ROOT = Path("/root/nox")
CONFIG = "config/owner_native_subagents.json"
REFILL = "scripts/owner_systemic_refill.py"
LOCK = ROOT / "state/owner_maintenance.lock"
SERVICE = "nox-dispatcher-t855u"
INSTANCE = 60509551
EXPECTED = {
    CONFIG: "01101f81e0b76e54a53f0f6c2734082ef164ae32b39832c6d74b154a809084e5",
    REFILL: "08b230ae02d0be832df68df53750c356a88b0c803f31562d9e8859697679437b",
}
HELPER_SHA = "8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609"
BUNDLE = __NOX_BUNDLE_JSON__


def hold(ok, reason):
    if not ok:
        raise RuntimeError("HOLD_REFILL_UPGRADE_" + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def bundle(name, expected_sha=None):
    value = BUNDLE.get(name)
    hold(isinstance(value, str) and len(value) <= 1400000, "BUNDLE_" + name.replace(".", "_"))
    raw = base64.b64decode(value, validate=True)
    hold(0 < len(raw) <= 1024 * 1024, "BUNDLE_SIZE")
    if expected_sha:
        hold(digest(raw) == expected_sha, "HELPER_PIN")
    compile(raw, name, "exec")
    return raw


def protected(h):
    names = ("nox-ds41-8098", "nox-proxy", "nox-web29-18775")
    result = {}
    for name in names:
        p = subprocess.run(["supervisorctl", "status", name],
                           capture_output=True, text=True, timeout=8)
        match = re.fullmatch(re.escape(name) + r"\s+RUNNING\s+pid\s+([0-9]+),.*",
                             p.stdout.strip())
        hold(p.returncode == 0 and match is not None, "PROTECTED_" + name.replace("-", "_"))
        ident = h.process_identity(int(match[1]))
        hold(ident is not None, "PROTECTED_PID")
        result[name] = ident
    return result


def assert_idle(h):
    state, active = h.queue_idle(ROOT)
    hold(not active, "ACTIVE_JOBS")
    for row in state["tasks"].values():
        if not isinstance(row, dict):
            continue
        lease = row.get("native_worker_lease")
        if row.get("status") in {"running", "retry", "admitted"} and isinstance(lease, dict) and lease:
            raise RuntimeError("HOLD_REFILL_UPGRADE_ACTIVE_LEASE")
    return digest(h.read_regular(ROOT / "state/dispatcher/state.json", 32 * 1024 * 1024))


def run():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    commit = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    hold(re.fullmatch(r"[1-9][0-9]{0,23}", request) is not None
         and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
         and os.environ.get("NOX_OWNER_ACTION") == "repair"
         and os.environ.get("NOX_OWNER_INSTANCE_ID") == str(INSTANCE),
         "OWNER_CONTEXT")
    hold(set(BUNDLE) == {"continuous_transaction_helpers.py", "owner_systemic_refill.py"},
         "BUNDLE_SET")
    helper_raw = bundle("continuous_transaction_helpers.py", HELPER_SHA)
    fresh = bundle("owner_systemic_refill.py")
    module = types.ModuleType("_nox_refill_upgrade_helper")
    exec(compile(helper_raw, "pinned_transaction_helper", "exec"), module.__dict__)
    h = module
    fresh_module = types.ModuleType("_nox_refill_upgrade_candidate")
    exec(compile(fresh, "pinned_refill_candidate", "exec"), fresh_module.__dict__)
    hold(callable(getattr(fresh_module, "acceptance_mapping_valid", None))
         and callable(getattr(fresh_module, "select_next", None))
         and callable(getattr(fresh_module, "validate_manifest", None)),
         "NEW_CONTRACT")
    receipt = {"schema": "NOX_REFILL_CONTRACT_UPGRADE_V1", "request": request,
               "source_sha": commit, "previous_sha256": EXPECTED[REFILL],
               "new_sha256": digest(fresh), "state": "PREFLIGHT",
               "original_task_accepted": False, "model_restarted": False,
               "s03_changed": False, "protected_restarts": 0}
    hold(h.stop_clear(ROOT), "STOP")
    hold(LOCK.is_file() and not LOCK.is_symlink(), "OWNER_LOCK")
    fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    locked = False
    stopped = False
    changed = False
    before = {}
    new = {}
    protected_before = {}
    children = {}
    queue_sha = None
    backup = ROOT / "state/dispatcher/refill_contract_upgrades" / request
    try:
        deadline = time.monotonic() + 12
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                hold(time.monotonic() < deadline and h.stop_clear(ROOT),
                     "OWNER_LEASE_BUSY")
                time.sleep(.2)
        info, named = os.fstat(fd), LOCK.stat()
        hold(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
             and info.st_nlink == 1 and not info.st_mode & 0o022
             and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
             "OWNER_LEASE_IDENTITY")
        hold(h.stop_clear(ROOT), "STOP")
        before = h.preimages(ROOT, EXPECTED)
        old_config = json.loads(before[CONFIG])
        hold(old_config.get("instance_id") == INSTANCE
             and old_config.get("owner_authorized") is True
             and old_config.get("execution_mode") == "NATIVE_PROJECT_V1"
             and old_config.get("target") == 3
             and old_config.get("global_worker_cap") == 3
             and old_config.get("mode") == "NORMAL"
             and old_config.get("module_pins", {}).get("owner_systemic_refill.py")
                 == EXPECTED[REFILL], "CONFIG_SCOPE")
        supervisor = h.supervisor("status")
        hold(supervisor["state"] == "RUNNING" and supervisor["pid"], "DIRECTOR_STATE")
        director = h.process_identity(supervisor["pid"])
        hold(director is not None, "DIRECTOR_IDENTITY")
        children = h.descendant_snapshot(director["pid"])
        hold(len(children) >= 3, "THREE_WORKERS_CENSUS")
        protected_before = protected(h)
        queue_sha = assert_idle(h)
        hold(not backup.exists() and not backup.is_symlink(), "ONE_SHOT_REUSED")
        config = dict(old_config)
        config["module_pins"] = dict(old_config["module_pins"])
        config["module_pins"]["owner_systemic_refill.py"] = digest(fresh)
        new = {REFILL: fresh, CONFIG: encoded(config)}
        backup.mkdir(parents=True, mode=0o700)
        h.atomic(backup / "owner_systemic_refill.py", before[REFILL], 0o600)
        h.atomic(backup / "owner_native_subagents.json", before[CONFIG], 0o600)
        h.atomic(backup / "queue_sha256.txt", (queue_sha + "\n").encode(), 0o600)
        hold(protected(h) == protected_before and h.stop_clear(ROOT), "SERVICE_CHANGED")
        hold(assert_idle(h) == queue_sha, "QUEUE_CHANGED")
        h.preimages(ROOT, EXPECTED)
        h.stop_checked()
        stopped = True
        h.wait_previous_descendants_stopped(children, timeout=10)
        hold(protected(h) == protected_before and h.stop_clear(ROOT), "PROTECTED_CHANGED")
        hold(assert_idle(h) == queue_sha, "QUEUE_CHANGED_AFTER_STOP")
        h.apply_transaction(ROOT, new, before)
        changed = True
        hold(h.read_regular(ROOT / REFILL) == fresh
             and h.read_regular(ROOT / CONFIG) == new[CONFIG], "WRITE_READBACK")
        receipt["state"] = "CONTRACT_MODULE_WRITTEN"
        fcntl.flock(fd, fcntl.LOCK_UN)
        locked = False
        identity = h.start_checked(ROOT, require_native_status=True)
        receipt["state"] = "CONTRACT_MODULE_RUNNING"
        receipt["director"] = {"pid": identity["pid"], "start_ticks": identity["start_ticks"]}
        hold(protected(h) == protected_before and h.stop_clear(ROOT),
             "PROTECTED_POST_START")
        current = h.preimages(ROOT, {REFILL: digest(fresh),
                                      CONFIG: digest(new[CONFIG])})
        hold(current[REFILL] == fresh and current[CONFIG] == new[CONFIG], "LIVE_READBACK")
        status = json.loads(h.read_regular(ROOT / "status/agents_t856u.json", 2 * 1024 * 1024))
        native = status.get("native_subexecutors", {})
        hold(len(native.get("workers") or []) == 3
             and native.get("director", {}).get("pid") == identity["pid"], "NATIVE_THREE")
        receipt["state"] = "PHYSICAL_REFILL_CONTRACT_RUNNING"
        print("NOX_MAINT_REFILL_CONTRACT=" + encoded(receipt).decode(), flush=True)
        print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
    except BaseException as exc:
        # Recover only if we changed the files and can prove no competing owner
        # and no new queue claims. Never overwrite drifted bytes.
        if changed:
            try:
                if not locked:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                h.stop_checked()
                hold(h.stop_clear(ROOT) and protected(h) == protected_before,
                     "ROLLBACK_PROTECTED")
                hold(assert_idle(h) == queue_sha, "ROLLBACK_QUEUE")
                hold(h.read_regular(ROOT / REFILL) == new[REFILL]
                     and h.read_regular(ROOT / CONFIG) == new[CONFIG],
                     "ROLLBACK_PREIMAGE")
                h.apply_transaction(ROOT, {REFILL: before[REFILL], CONFIG: before[CONFIG]}, new)
                fcntl.flock(fd, fcntl.LOCK_UN)
                locked = False
                h.start_checked(ROOT, require_native_status=True)
                receipt["state"] = "ROLLED_BACK_ORIGINAL_RESTARTED"
            except BaseException:
                receipt["state"] = "HOLD_UPGRADE_ROLLBACK_NOT_VERIFIED"
        elif stopped:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                locked = False
                h.start_checked(ROOT, require_native_status=True)
                receipt["state"] = "UNMODIFIED_ORIGINAL_RESTARTED"
            except BaseException:
                receipt["state"] = "HOLD_UPGRADE_ORIGINAL_RESTART_NOT_VERIFIED"
        print("NOX_MAINT_REFILL_CONTRACT=" + encoded(receipt).decode(), flush=True)
        raise
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == "__main__":
    run()
