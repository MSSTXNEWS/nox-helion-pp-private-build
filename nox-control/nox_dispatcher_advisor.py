#!/usr/bin/env python3
"""Read-only optimization hints for the EXISTING NOX dispatcher.
Never submits a job, never changes training weights, never disables STOP.
Input is locally collected evidence: metrics, queue and trainer receipts.
"""
import argparse
import datetime as dt
import json
import math
import os
import tempfile
import stat
from pathlib import Path


def _finite_nonnegative(value):
    # Owner telemetry may contain JSON booleans, NaN/Infinity, or strings.
    # They must never authorize progress or crash read-only diagnostics.
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _owner_snapshot_attested(snapshot, verifier):
    """Only an injected, trusted owner-side verifier can attest JSON evidence.

    A JSON 'age', lease or CAS flag alone is never proof of provenance.
    The command-line advisor deliberately has no verifier and fails closed.
    """
    if not callable(verifier):
        return False
    try:
        return verifier(snapshot) is True
    except Exception:
        return False


def assess(snapshot, *, owner_snapshot_verifier=None):
    issues = []
    def add(code, urgency, advice, question=None):
        item = {"code": code, "urgency": urgency, "advice": advice}
        if question:
            item["question"] = question
        issues.append(item)
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a JSON object")
    stop_state = snapshot.get("stop_active")
    if stop_state is True:
        add("STOP_ACTIVE", "safety", "Keep training and automatic mutations paused.")
        return issues
    if stop_state is not False:
        add("STOP_STATE_UNVERIFIED", "hold",
            "Do not advise optimization, training or native publication until "
            "a current authenticated owner STOP reading is explicitly false.")
        return issues
    required = ("onehost", "s03", "trainer", "gpu", "disk")
    missing = [x for x in required if not isinstance(snapshot.get(x), dict)]
    if missing:
        add("TELEMETRY_MISSING", "hold", "Do not infer healthy services from missing metrics.",
            "Provide authenticated current metrics for: " + ", ".join(missing))
        return issues
    onehost, s03, trainer, gpu, disk = [snapshot[x] for x in required]
    native = snapshot.get("native_queue")
    # 6A02: A partially populated dict is not a usable native owner snapshot.
    # Check the same essential fields used by existing lease, worker and
    # resource gates. A plain JSON flag alone still cannot attest provenance.
    native_complete = (
        isinstance(native, dict)
        and isinstance(native.get("admission_state"), str)
        and bool(native["admission_state"].strip())
        and type(native.get("jobs_started")) is int
        and native["jobs_started"] >= 0
        and isinstance(native.get("workers"), list)
        and 0 < len(native["workers"]) <= 3
        and all(isinstance(w, dict)
                and isinstance(w.get("state"), str) and bool(w["state"])
                and "current_task" in w for w in native["workers"])
        and type(native.get("maintenance_busy")) is bool
        and type(native.get("active_claims")) is bool
        and type(native.get("resource_headroom_bytes")) is int
        and native["resource_headroom_bytes"] >= 0
        and type(native.get("owner_evidence_age_sec")) is int
        and 0 <= native["owner_evidence_age_sec"] <= 30
        and native.get("owner_lease_cas_verified") is True
        and native.get("immutable_task_source_verified") is True
    )
    if isinstance(native, dict):
        workers = native.get("workers")
        state = native.get("admission_state")
        if (state == "NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED"
                and type(native.get("jobs_started")) is int
                and native["jobs_started"] == 0
                and isinstance(workers, list) and 0 < len(workers) <= 3
                and all(isinstance(w, dict)
                        and w.get("state") == "RUNNING"
                        and w.get("current_task") is None for w in workers)):
            # Original 6A02: idle workers are *not* an owner lease, task claim,
            # atomic registry snapshot, or sufficient resource admission.
            headroom = native.get("resource_headroom_bytes")
            # The verifier must check this SAME snapshot's owner provenance,
            # timestamp and lease/CAS; it cannot be supplied through JSON.
            owner_attested = _owner_snapshot_attested(
                snapshot, owner_snapshot_verifier)
            reviewable = (
                owner_attested
                and native.get("maintenance_busy") is False
                and native.get("active_claims") is False
                and type(headroom) is int and headroom >= 2*1024**3
                # A previously true lease/source flag is not a current owner
                # admission. Require a bounded age from the same snapshot.
                and type(native.get("owner_evidence_age_sec")) is int
                and 0 <= native["owner_evidence_age_sec"] <= 30
                and native.get("owner_lease_cas_verified") is True
                and native.get("immutable_task_source_verified") is True
            )
            if reviewable:
                add("NATIVE_REFILL_OWNER_REVIEW_REQUIRED", "review",
                    "Candidate only: revalidate current STOP, owner lease/CAS, exact "
                    "TaskID dedup, resource floor and pinned source at the native "
                    "publisher immediately before ONE action. This advice is not admission.")
            else:
                add("NATIVE_REFILL_OWNER_HOLD", "hold",
                    "Idle workers/catalog exhaustion do not authorize publication. "
                    "Await independently attested owner snapshot, age-bounded lease/CAS evidence, immutable source, zero active claims, "
                    "explicit maintenance clearance and >=2 GiB raw cgroup headroom; "
                    "do not duplicate queues or overwrite a pending run.")
        if native.get("maintenance_busy") is True or native.get("active_claims") is True:
            add("NATIVE_OWNER_LEASE_BUSY", "hold",
                "Do not cancel/replace a live claim or force a second publisher. Reconcile the existing owner lease and exact TaskID receipt, then retry once on new owner state.")
        headroom = native.get("resource_headroom_bytes")
        if type(headroom) is not int or headroom < 0:
            add("NATIVE_CGROUP_MEMORY_UNVERIFIED", "hold",
                "No verified raw cgroup headroom; deny extra native admission until current owner evidence.")
        elif headroom < 2*1024**3:
            add("NATIVE_CGROUP_MEMORY_PRESSURE", "urgent",
                "Keep the serving model, S03 and STOP intact. Native CPU work only with fresh low-memory admission; defer extra model/worker/RAM staging until measured headroom recovers.")
    if onehost.get("healthy") is not True:
        add("ONEHOST_DEGRADED", "urgent", "Inspect OneHost health and preserve single dispatcher; repair only by local allowlist.")
    if s03.get("readback_verified") is not True:
        add("S03_NOT_VERIFIED", "hold", "Do not claim persistent memory; verify SQLite integrity and restart readback.")
    temp = gpu.get("temperature_c")
    if "temperature_c" in gpu and not _finite_nonnegative(temp):
        add("GPU_THERMAL_READING_INVALID", "safety",
            "Invalid GPU temperature measurement; refuse new training until an authenticated sensor readback.")
    elif _finite_nonnegative(temp) and temp >= 70:
        add("GPU_THERMAL_LIMIT", "safety", "Hold new training admission; use existing host SAFE70 and sensor policy.")
    if gpu.get("temperature_sensor_valid") is not True:
        add("GPU_SENSOR_MISSING", "safety", "Do not train until trusted thermal telemetry is restored.")
    free_gib = disk.get("free_gib")
    reserve_gib = disk.get("checkpoint_reserve_gib", 10)
    if free_gib is None:
        add("DISK_UNKNOWN", "hold", "Inspect free disk and checkpoint reserve before training.")
    elif not _finite_nonnegative(free_gib) or not _finite_nonnegative(reserve_gib):
        add("DISK_TELEMETRY_UNVERIFIED", "hold",
            "Non-finite, negative or wrongly typed disk/reserve telemetry; no downloads or training admission.")
    elif free_gib < max(5, reserve_gib):
        add("DISK_CHECKPOINT_RESERVE", "urgent", "Pause new downloads and training admission; preserve existing weights, S03 and checkpoints.")
    if trainer.get("running") is True and trainer.get("checkpoint_recent") is not True:
        add("TRAIN_CHECKPOINT_STALE", "urgent", "Inspect trainer heartbeat and checkpoint write/readback; avoid blind restart.")
    if trainer.get("running") is False and trainer.get("ready_for_resume") is True:
        # 0A01: a cached trainer resume flag must not be mistaken for current
        # owner STOP, S03/checkpoint and resource admission evidence. This
        # advisor does not schedule or resume training.
        resume_evidence_ok = (
            onehost.get("healthy") is True
            # First live chat outranks a merely cached training-resume flag.
            # Unverified/waiting chat or stale/over-budget p95 is a HOLD.
            and onehost.get("chat_waiting") is False
            and _finite_nonnegative(onehost.get("chat_p95_ms"))
            and _finite_nonnegative(onehost.get("chat_budget_ms"))
            and onehost["chat_budget_ms"] > 0
            and onehost["chat_p95_ms"] < onehost["chat_budget_ms"]
            and _finite_nonnegative(onehost.get("chat_metrics_age_sec"))
            and onehost["chat_metrics_age_sec"] <= 30
            and s03.get("readback_verified") is True
            and trainer.get("checkpoint_recent") is True
            and gpu.get("temperature_sensor_valid") is True
            and _finite_nonnegative(temp) and temp < 70
            and _finite_nonnegative(free_gib)
            and _finite_nonnegative(reserve_gib)
            and free_gib >= max(5, reserve_gib)
            # 0A01: an owner-attested partial queue dict is not a complete
            # admission snapshot. Use the exact 6A02 completeness contract
            # (worker identities, immutable source, claims and fresh CAS)
            # before even advertising a training-resume review candidate.
            and native_complete
            and native.get("maintenance_busy") is False
            and native.get("active_claims") is False
            and type(native.get("resource_headroom_bytes")) is int
            and native["resource_headroom_bytes"] >= 2 * 1024**3
            # A signed but stale native owner observation cannot support even
            # a training-resume review hint. Match the bounded age/CAS gate
            # used for existing native REFILL advice; this is NOT admission.
            and type(native.get("owner_evidence_age_sec")) is int
            and 0 <= native["owner_evidence_age_sec"] <= 30
            and native.get("owner_lease_cas_verified") is True
            and _owner_snapshot_attested(snapshot, owner_snapshot_verifier)
        )
        if resume_evidence_ok:
            add("TRAIN_RESUME_CANDIDATE", "review",
                "Owner-attested source observation only: recheck STOP, trainer "
                "lease/CAS, S03, checkpoint and resource admission at the existing "
                "OneHost immediately before any resume. Never launch another scheduler.")
        else:
            add("TRAIN_RESUME_OWNER_HOLD", "hold",
                "Cached ready_for_resume is not training admission. Require "
                "independent current owner attestation, verified S03/checkpoint, "
                "SAFE70 sensor, disk, fresh under-budget idle chat, and >=2 GiB "
                "cgroup headroom, idle claims and maintenance clearance; "
                "do not enqueue or resume.")
    if onehost.get("chat_waiting") is True and trainer.get("running") is True:
        # 6A03: chat priority is not a license to preempt a live optimizer.
        # Only an authenticated, completed optimizer-step/embedding-batch
        # boundary with a durable checkpoint+cursor may be suggested for
        # owner review. No signals, scheduler changes or resumes here.
        import re
        cursor = trainer.get("resume_cursor_sha256")
        safe_yield_review = (
            trainer.get("yield_boundary") in ("optimizer_step", "embedding_batch")
            and trainer.get("yield_boundary_complete") is True
            and type(trainer.get("yield_step")) is int
            and trainer["yield_step"] >= 0
            and isinstance(cursor, str)
            and re.fullmatch(r"[0-9a-f]{64}", cursor) is not None
            and trainer.get("checkpoint_readback_verified") is True
            and trainer.get("yield_owner_lease_cas_verified") is True
            and isinstance(native, dict)
            and native.get("maintenance_busy") is False
            and native.get("owner_lease_cas_verified") is True
            and type(native.get("owner_evidence_age_sec")) is int
            and 0 <= native["owner_evidence_age_sec"] <= 30
            and _owner_snapshot_attested(snapshot, owner_snapshot_verifier)
        )
        if safe_yield_review:
            add("CHAT_PRIORITY", "review",
                "Completed cooperative boundary with owner-attested checkpoint "
                "and resume cursor: owner may review ONE soft yield of the "
                "existing training claim. Recheck live STOP, PID/startticks, "
                "lease/CAS and cursor before acting; no automatic action.")
        else:
            add("CHAT_PRIORITY", "hold",
                "Chat takes priority, but a completed optimizer-step or embedding "
                "batch, checkpoint readback, resume cursor and current owner "
                "lease/CAS attestation are unverified. No signal, hard STOP, "
                "trainer restart or cursor advance; await a safe boundary.")
    if trainer.get("running") is True:
        # Original TaskID 6A04: missing/malformed utilization is a HOLD,
        # not silent evidence of capacity or an unhandled huge-int overflow.
        util = gpu.get("utilization_pct")
        if not _finite_nonnegative(util) or util > 100:
            add("GPU_UTILIZATION_UNVERIFIED", "hold",
                "Missing, invalid or out-of-range GPU utilization; do not "
                "infer spare GPU capacity or admit additional work.")
        elif util < 35 and (gpu.get("temperature_sensor_valid") is not True
                              or not _finite_nonnegative(temp) or temp >= 70):
            # A broken or hot sensor must never accompany a "spare GPU" hint.
            # SAFE70 and active training are owned by the native host; source
            # advice cannot authorize additional work.
            add("GPU_RESIDUAL_THERMAL_HOLD", "hold",
                "GPU thermal evidence is missing, invalid or at SAFE70. "
                "Do not suggest residual GPU capacity or admit extra work.")
        elif util < 35 and (onehost.get("healthy") is not True
                              or s03.get("readback_verified") is not True):
            # Serving continuity outranks opportunistic GPU use. Even a
            # healthy sensor and low utilization cannot imply spare capacity
            # while chat or durable memory is degraded.
            add("GPU_RESIDUAL_SERVICE_HOLD", "hold",
                "OneHost health or S03 readback is unverified. Do not suggest "
                "residual GPU capacity before serving continuity is restored.")
        elif util < 35 and isinstance(native, dict) and (
                native.get("active_claims") is True
                or native.get("maintenance_busy") is True):
            # A live owner claim or maintenance window outranks speculative
            # GPU slack. Do not recommend residual capacity from a quiet
            # instant while an existing native action owns the resources.
            add("GPU_RESIDUAL_OWNER_BUSY_HOLD", "hold",
                "Active native claim or maintenance window: no residual GPU "
                "capacity hint. Keep the existing owner lease and work intact.")
        elif util < 35 and (not isinstance(native, dict)
                              or native.get("active_claims") is not False
                              or native.get("maintenance_busy") is not False):
            # Missing or malformed owner-claim/maintenance evidence is not
            # evidence of idle resources. In particular, 0/1/string/None
            # must not silently bypass the exact-boolean owner gate.
            add("GPU_RESIDUAL_OWNER_UNVERIFIED", "hold",
                "Owner claims or maintenance clearance is missing or non-boolean. "
                "Low GPU utilization cannot imply spare capacity; no new GPU admission.")
        elif util < 35:
            # Low compute utilization alone is NOT spare accelerator capacity
            # without fresh VRAM, host I/O and chat latency.
            host = snapshot.get("cpu_io")
            values = (
                (gpu.get("vram_used_mib"), 0, 1048576),
                (gpu.get("vram_total_mib"), 1, 1048576),
                (gpu.get("age_sec"), 0, 30),
                ((host or {}).get("cpu_busy_pct") if isinstance(host,dict) else None, 0, 100),
                ((host or {}).get("io_wait_pct") if isinstance(host,dict) else None, 0, 100),
                ((host or {}).get("age_sec") if isinstance(host,dict) else None, 0, 30),
                (onehost.get("chat_p95_ms"), 0, 300000),
                (onehost.get("chat_budget_ms"), 1, 300000),
                (onehost.get("chat_metrics_age_sec"), 0, 30),
            )
            # Owner telemetry can contain JSON integers too large for
            # math.isfinite(int); keep those on the existing HOLD path.
            known = (all(_finite_nonnegative(v) and lo <= v <= hi
                         for v,lo,hi in values)
                     and type(onehost.get("chat_waiting")) is bool)
            if not known or gpu["vram_used_mib"] >= gpu["vram_total_mib"]:
                add("GPU_RESIDUAL_UNVERIFIED", "hold",
                    "GPU utilization alone cannot justify more work: require fresh "
                    "VRAM, CPU, I/O and chat latency measurements. Admit no GPU job.")
            elif onehost["chat_waiting"] or onehost["chat_p95_ms"] >= onehost["chat_budget_ms"]:
                # CHAT_PRIORITY was already emitted for a waiting chat above.
                if not onehost["chat_waiting"]:
                    add("GPU_CHAT_PRIORITY", "hold",
                        "Chat latency at its budget takes priority; no GPU spare allocation.")
            elif host["cpu_busy_pct"] >= 85 or host["io_wait_pct"] >= 10:
                add("GPU_HOST_PIPELINE_PRESSURE", "hold",
                    "Host CPU/I/O pressure blocks further GPU work despite low compute utilization.")
            elif (not native_complete
                    or type(native.get("resource_headroom_bytes")) is not int
                    or native["resource_headroom_bytes"] < 2 * 1024**3
                    or type(native.get("owner_evidence_age_sec")) is not int
                    or not 0 <= native["owner_evidence_age_sec"] <= 30
                    or native.get("owner_lease_cas_verified") is not True):
                # A quiet GPU with cgroup pressure or stale/unknown owner
                # authority is not capacity. Keep the cgroup floor consistent
                # with the existing 6A02/0A01 native owner review gates.
                add("GPU_RESIDUAL_RESOURCE_HOLD", "hold",
                    "Low utilization is not spare GPU capacity while raw cgroup "
                    "headroom is below 2 GiB, the native queue snapshot is "
                    "incomplete, or attested owner lease/CAS is stale or absent. "
                    "No new GPU work admitted.")
            elif not _owner_snapshot_attested(snapshot, owner_snapshot_verifier):
                # Raw JSON claims of idle leases and fresh sensors are not
                # authenticated owner evidence. Never call these "measured"
                # spare resources without attesting the exact snapshot.
                add("GPU_RESIDUAL_SOURCE_UNATTESTED", "hold",
                    "Low-utilization telemetry is not owner-attested. Recheck the "
                    "exact snapshot with the trusted owner verifier before "
                    "reporting spare GPU observations; no new work is admitted.")
            else:
                cap = round(85 - util, 2)
                add("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", "observe",
                    f"Measured utilization-only upper bound to the 85% limit: {cap} percentage points. "
                    "VRAM is not a per-job allocation; no admission, trainer restart or new queue authorized.")
    if not issues:
        # If another concrete issue already exists, preserve its established
        # diagnostic code (including GPU/thermal and memory checks). Only a
        # falsely CLEAN report needs the missing-queue/attestation HOLD.
        if not native_complete or not _owner_snapshot_attested(
                snapshot, owner_snapshot_verifier):
            add("NATIVE_QUEUE_UNVERIFIED", "hold",
                "Native owner queue, workers, immutable source or fresh "
                "authenticated lease/CAS evidence is missing or incomplete. "
                "No native admission or unverified clean diagnostic.")
        else:
            add("NO_UNVERIFIED_TUNING", "observe",
                "No changes recommended without measured before/after and readback.")
    return issues

def _unique_json_pairs(pairs):
    """Reject duplicate keys at every depth: later STOP/lease values cannot shadow earlier ones."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate owner telemetry JSON key")
        result[key] = value
    return result


def _reject_json_constant(value):
    """JSON NaN/Infinity are not valid authenticated telemetry."""
    raise ValueError("nonfinite owner telemetry JSON constant")


MAX_OWNER_SNAPSHOT_BYTES = 4 * 1024 * 1024


def _read_snapshot_json(path):
    """Read bounded owner evidence from one regular inode, never follow a final symlink.

    This is only untrusted advisory input; even a valid file does not attest
    STOP/lease/CAS or authorize a native action.
    """
    try:
        if not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("safe no-follow read unavailable")
        flags = (os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_OWNER_SNAPSHOT_BYTES:
                raise ValueError("owner snapshot must be a bounded regular file")
            raw = bytearray()
            while len(raw) <= MAX_OWNER_SNAPSHOT_BYTES:
                part = os.read(fd, min(65536, MAX_OWNER_SNAPSHOT_BYTES + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            if len(raw) > MAX_OWNER_SNAPSHOT_BYTES:
                raise ValueError("owner snapshot exceeds size bound")
            after = os.fstat(fd)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(before) != identity(after):
                raise ValueError("owner snapshot changed during read")
        finally:
            os.close(fd)
        data = json.loads(
            raw.decode("utf8"),
            object_pairs_hook=_unique_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError):
        # Neither malformed, oversized nor raced input can yield advice that
        # might be mistaken for owner-attested permission to write.
        raise SystemExit("HOLD_OWNER_TELEMETRY_JSON_INVALID") from None
    if not isinstance(data, dict):
        raise SystemExit("HOLD_OWNER_TELEMETRY_JSON_INVALID")
    return data


def _write_report(snapshot_path, output_path, report):
    """Write a complete advisor receipt or none; never replace its evidence."""
    source = Path(snapshot_path)
    path = Path(output_path)
    if path.resolve() == source.resolve():
        raise SystemExit("HOLD_OWNER_ADVICE_OUTPUT_COLLISION")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SystemExit("HOLD_OWNER_ADVICE_OUTPUT_UNSAFE")
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf8", dir=path.parent,
            prefix="." + path.name + ".", suffix=".tmp", delete=False
        ) as handle:
            pending = Path(handle.name)
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # A consumer sees either the previous complete JSON receipt or the
        # new complete receipt. A failed writer leaves the old one intact.
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    data = _read_snapshot_json(args.snapshot)
    report = {"schema_version":1,"observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "mode":"read_only", "advice": assess(data)}
    _write_report(args.snapshot, args.output, report)
    print(json.dumps(report,ensure_ascii=False))

if __name__ == "__main__":
    main()
