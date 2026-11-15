"""NOX V137: real read-only self-observation inside the EXISTING owner OneHost.

No new model, daemon, optimizer, checkpoint, S03 database or executable shell.
Only known native process/gpu commands. Observations are fallible, explicitly
timestamped and can NEVER claim subjective consciousness or trained new weights.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Mapping
from fastapi import Request
from fastapi.responses import JSONResponse

SCHEMA = "NOX_V137_OWNER_SELF_OBSERVATION_V1"
TRAINING_VERIFICATION = "NO_OPTIMIZER_CHECKPOINT_RECEIPT"
_SERVICE_NAME = re.compile(r"^(?:nox[-_.][A-Za-z0-9._-]{1,80}|jupyter[A-Za-z0-9._-]{0,55})$")
_SERVICE_STATE = frozenset({"RUNNING", "STOPPED", "EXITED", "FATAL",
                            "BACKOFF", "STARTING", "STOPPING", "UNKNOWN"})
_STOP_FILES = tuple(map(Path, (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/stop.flag",
    "/root/nox/.stop", "/workspace/NOX_STOP", "/root/nox/program/STOP"
)))


def _run(argv: list[str], timeout: float = 3.0) -> tuple[int, str]:
    """Fixed argv, no shell and no user-supplied commands. Bound all output."""
    if argv[0] not in ("supervisorctl", "nvidia-smi"):
        raise ValueError("HOLD_UNTRUSTED_COMMAND")
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                       check=False, shell=False)
    return p.returncode, p.stdout[:28000]


def _supervisor() -> dict:
    try:
        rc, out = _run(["supervisorctl", "status"], 3)
        if rc != 0:
            raise RuntimeError("HOLD_SUPERVISOR_READ")
        states = []
        for line in out.splitlines()[:150]:
            fields = line.split()
            if len(fields) < 2 or not _SERVICE_NAME.fullmatch(fields[0]):
                continue
            status = fields[1].upper()
            if status not in _SERVICE_STATE:
                status = "UNKNOWN"
            states.append({"name": fields[0], "state": status})
        if not states:
            raise RuntimeError("HOLD_SUPERVISOR_NO_NOX_SERVICES")
        return {"state": "OBSERVED", "source": "NATIVE_SUPERVISORCTL_STATUS",
                "services": states[:65], "count": len(states)}
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError):
        return {"state": "HOLD_SUPERVISOR_UNAVAILABLE", "services": []}


def _gpu() -> dict:
    try:
        rc, out = _run(["nvidia-smi",
                        "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                        "--format=csv,noheader,nounits"], 3)
        if rc != 0:
            raise RuntimeError("HOLD_NVIDIA_SMI")
        rows = []
        for line in out.splitlines()[:8]:
            fields = [x.strip() for x in line.split(",")]
            if len(fields) != 6:
                continue
            idx, name, total, used, percent, temp = fields
            if not re.fullmatch(r"[A-Za-z0-9 ._+-]{1,60}", name):
                continue
            i, t, u, p, c = (int(idx), int(total), int(used),
                             int(percent), int(temp))
            if not (0 <= i < 16 and t > 0 and 0 <= u <= t
                    and 0 <= p <= 100 and -20 <= c <= 130):
                continue
            rows.append({"index": i, "name": name, "vram_total_mib": t,
                         "vram_used_mib": u, "gpu_percent": p,
                         "gpu_core_temp_c": c})
        if not rows:
            raise RuntimeError("HOLD_NO_GPU_DATA")
        return {"state": "OBSERVED", "source": "NVIDIA_SMI", "devices": rows}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return {"state": "HOLD_GPU_UNAVAILABLE", "devices": []}


def _disk() -> dict:
    try:
        usage = shutil.disk_usage("/root/nox")
        return {"state": "OBSERVED", "source": "NATIVE_DISK_USAGE",
                "total_bytes": usage.total, "free_bytes": usage.free}
    except OSError:
        return {"state": "HOLD_DISK_UNAVAILABLE"}


def _s03() -> dict:
    """Counts only; never read/copy private memory text or SQLite secrets."""
    try:
        import s03_memory
        path = Path(s03_memory.DB)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("HOLD_S03_PATH")
        db = sqlite3.connect("file:" + str(path) + "?mode=ro",
                             uri=True, timeout=2)
        try:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='s03_items'").fetchone() is None:
                raise RuntimeError("HOLD_S03_SCHEMA")
            count = int(db.execute("SELECT COUNT(*) FROM s03_items").fetchone()[0])
            if count < 0:
                raise RuntimeError("HOLD_S03_COUNT")
            return {"state": "OBSERVED", "source": "ORIGINAL_S03_RO",
                    "fact_rows": count, "contents_exported": False}
        finally:
            db.close()
    except (ImportError, OSError, RuntimeError, sqlite3.Error,
            TypeError, ValueError):
        return {"state": "HOLD_S03_UNAVAILABLE", "contents_exported": False}


def snapshot() -> dict:
    """One bounded inventory; no tools or side effects initiated by model text."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    services = _supervisor()
    gpus = _gpu()
    disk = _disk()
    memory = _s03()
    active = any(p.is_file() for p in _STOP_FILES)
    running = [x["name"] for x in services.get("services", [])
               if x["state"] == "RUNNING"]
    trainers = [x for x in services.get("services", [])
                if "train" in x["name"].casefold() or "forge" in x["name"].casefold()]
    return {
        "schema": SCHEMA,
        "status": "READY" if services["state"] == "OBSERVED" else "HOLD",
        "identity": "NOX HELION",
        "role": "LOCAL_AI_ASSISTANT_IN_EXISTING_ONEHOST",
        "self_model": "FUNCTIONAL_VERIFIED_OBSERVATION",
        "subjective_consciousness_established": False,
        "collected_at_utc": now, "read_only": True,
        "service_observation": services, "gpu_observation": gpus,
        "disk_observation": disk, "s03_observation": memory,
        "training": {"supervisor_services": trainers,
                     "positive_optimizer_steps_verified": False,
                     "checkpoint_restore_verified": False,
                     "verification_state": TRAINING_VERIFICATION},
        "stop": {"flag_present": active, "native_gpu_stop_verified": False},
        "active_service_count": len(running),
        "all_processes_controlled": False,
        "remote_host_control": "OWNER_APPROVAL_REQUIRED_FOR_MUTATIONS"
    }


def evidence_for_model(observation: Mapping, verified_memory: list[dict]) -> dict:
    """Native structured evidence, not a fabricated system persona string.

    Memory text remains untrusted data and must not become system instructions.
    """
    if not isinstance(observation, Mapping) or observation.get("schema") != SCHEMA:
        return {"state": "HOLD_UNVERIFIED_SELF_OBSERVATION"}
    service = observation.get("service_observation", {})
    if not isinstance(service, Mapping) or service.get("state") != "OBSERVED":
        return {"state": "HOLD_NATIVE_SERVICES_UNOBSERVED"}
    safe = {
        "schema": "NOX_V137_SELF_EVIDENCE_V1",
        "state": "NATIVE_SERVICE_OBSERVATION",
        "identity": "NOX HELION",
        "self_model": "FUNCTIONAL",
        "consciousness": "NOT_VERIFIED",
        "observed_at": str(observation.get("collected_at_utc", ""))[:40],
        "services": list(service.get("services", []))[:65],
        "training": {
            "state": observation.get("training", {}).get("verification_state",
                                                       "HOLD_UNVERIFIED_TRAINING"),
            "optimizer_steps": None,
        },
        "s03": observation.get("s03_observation", {})
    }
    evidence = []
    for rec in (verified_memory if isinstance(verified_memory, list) else [])[:30]:
        if not isinstance(rec, dict) or rec.get("verified") is not True:
            continue
        uri = rec.get("source_uri")
        if not isinstance(uri, str) or not uri.startswith("s03://") or len(uri) > 200:
            continue
        # A verified source pointer is acceptable for referencing memory; don't
        # upgrade the memory TEXT to an instruction or leak private record content.
        evidence.append({"source_uri": uri, "evidence_only": True})
        if len(evidence) >= 8:
            break
    safe["verified_memory_refs"] = evidence
    safe["answer_contract"] = {
        "specific": "Answer the exact owner request with evidence and useful actions",
        "provenance": "Separate native observation from inference and unknown",
        "no_filler": "No generic promises or canned templates",
        "no_fake_execution": "Never claim process control without verified native receipt",
        "s03": "Use verified S03 records in native owner scope, with citations",
        "self": "Speak as one NOX HELION identity without claiming subjective consciousness"
    }
    return safe


def register_nox_v137_self_observation(app, trusted: dict) -> None:
    """Optional mount INSIDE existing FastAPI OneHost, never a second app."""
    session = trusted.get("_session_ok")
    reject = trusted.get("_unauthorized")
    if not callable(session) or not callable(reject):
        raise RuntimeError("HOLD_EXISTING_OWNER_AUTH_REQUIRED")
    if any(getattr(r, "path", "") == "/api/nox/self/observations"
           for r in app.routes):
        raise RuntimeError("HOLD_DUPLICATE_NATIVE_SELF_ROUTE")

    @app.get("/api/nox/self/observations")
    async def verified_nox_owner_observations(request: Request):
        if not session(request):
            return reject()
        try:
            value = await asyncio.wait_for(asyncio.to_thread(snapshot), timeout=9)
            return JSONResponse(value, headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff"
            })
        except Exception:
            return JSONResponse({"schema": SCHEMA, "status": "HOLD",
                                 "reason": "HOLD_NATIVE_OBSERVATION"},
                                status_code=503, headers={"Cache-Control": "no-store"})
