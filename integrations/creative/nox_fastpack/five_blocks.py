"""Additive CS5 B01-B05 project journal inside the EXISTING NOX Creative worker.

There is no HTTP listener, installer, second model hub or global UI here.
Existing Studio._project owns the project path, STOP and user data boundary.
"""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

_LOCK = threading.RLock()
_SCHEMA = "NOX_CS5_PROJECT_EVENTS_V1"
_BLOCKS = {
    "B01": {"hypothesis", "research"},
    "B02": {"idea", "bible", "editorial"},
    "B03": {"production", "asset"},
    "B04": {"model_note"},
    "B05": {"brand", "publication_draft", "revenue_scenario", "receipt"},
}
_MAX_EVENTS = 200
_MAX_FILE = 1_500_000


def _digest(entry):
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _project_writer_lock(path):
    """Fail closed if another NOX host is committing this project."""
    lock = path.parent / ".cs5-project.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError("CS5_CONCURRENT_WRITER_HOLD") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{os.getpid()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def _journal_path(studio, project_id):
    folder = studio._project(project_id)  # Existing NOX path/ID guards.
    path = folder / "cs5_project_events.json"
    if path.is_symlink() or folder.is_symlink():
        raise ValueError("CS5_PROJECT_LINK_HOLD")
    return path


def _read(path):
    if not path.exists():
        return {"schema": _SCHEMA, "events": []}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE:
        raise ValueError("CS5_PROJECT_FILE_HOLD")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("schema") != _SCHEMA:
        raise ValueError("CS5_SCHEMA_HOLD")
    events = state.get("events")
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise ValueError("CS5_EVENT_BUDGET_HOLD")
    prev = ""
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("CS5_EVENT_CORRUPT")
        unsigned = {key: val for key, val in event.items() if key != "sha256"}
        if event.get("prev_sha256") != prev or event.get("sha256") != _digest(unsigned):
            raise ValueError("CS5_EVENT_CHAIN_HOLD")
        prev = event["sha256"]
    return state


def _write(path, state, *, stopped):
    data = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > _MAX_FILE:
        raise ValueError("CS5_PROJECT_SIZE_HOLD")
    fd, tmp = tempfile.mkstemp(prefix=".cs5-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ValueError("CS5_PROJECT_LINK_HOLD")
        # Do not publish bytes if STOP arrived during disk flush.
        if stopped():
            raise ValueError("CS5_STOP_ACTIVE")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def dispatch_five(studio, request):
    """Only the existing native worker calls this from its trusted dispatch."""
    action = request.get("action")
    if action == "cs5_research":
        from .public_research import research
        return research(studio, request)
    if action == "cs5_overview":
        return {
            "status": "LOCAL_ADAPTER_READY_NOT_E11_ADMITTED",
            "blocks": {key: sorted(value) for key, value in _BLOCKS.items()},
            "owner": "EXISTING_NOX_CREATIVE_WORKER",
            "ai": "USE_EXISTING_OLLAMA",
            "models": "USE_EXISTING_P03_MODELCENTER",
            "backup": "USE_EXISTING_OWNER_BACKUP; RESTIC_OPTIONAL",
            "production": "USE_EXISTING_STORYBOARD_COMFY_FFMPEG",
            "publication": "NO_EXTERNAL_PUBLISHER_CONNECTED",
        }
    if action not in ("cs5_list", "cs5_append", "cs5_export"):
        raise ValueError("CS5_UNKNOWN_ACTION")
    project_id = request.get("project_id")
    if not isinstance(project_id, str):
        raise ValueError("CS5_PROJECT_ID_REQUIRED")
    with _LOCK:
        path = _journal_path(studio, project_id)
        if action == "cs5_list":
            state = _read(path)
            # Stable absolute position, not a guessed page count, so a concurrent
            # append cannot silently shift older events to a different page.
            total = len(state["events"])
            before = request.get("before", total)
            if type(before) is not int or before < 0 or before > total:
                raise ValueError("CS5_HISTORY_CURSOR_HOLD")
            first = max(0, before - 20)
            selected = state["events"][first:before]
            return {"status": "LOCAL_RECORDS_NOT_E11", "project_id": project_id,
                    "events": selected, "count": total, "showing": len(selected),
                    "start_index": first, "next_before": first if first else None}
        with _project_writer_lock(path):
            if action == "cs5_export":
                return _export_project(studio, path, project_id)
            return _append_with_lock(studio, request, path)


def _append_with_lock(studio, request, path):
    state = _read(path)
    if studio._stop_event.is_set():
        raise ValueError("CS5_STOP_ACTIVE")
    block = request.get("block")
    kind = request.get("kind")
    text = request.get("text")
    url = request.get("source_url", "")
    if block not in _BLOCKS or kind not in _BLOCKS[block]:
        raise ValueError("CS5_BLOCK_KIND_HOLD")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000:
        raise ValueError("CS5_TEXT_LIMIT")
    if not isinstance(url, str) or len(url) > 600:
        raise ValueError("CS5_SOURCE_URL_HOLD")
    if url:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("https", "http") or not parsed.hostname or
            parsed.username or parsed.password or
            any(ord(char) < 32 for char in url)):
            raise ValueError("CS5_SOURCE_URL_HOLD")
    if len(state["events"]) >= _MAX_EVENTS:
        raise ValueError("CS5_EVENT_BUDGET_HOLD")
    evidence = ("HYPOTHESIS" if kind == "hypothesis" else
                "REPORTED_UNVERIFIED" if kind == "receipt" else "LOCAL_RECORD_ONLY")
    previous = state["events"][-1]["sha256"] if state["events"] else ""
    event = {
        "event_id": uuid.uuid4().hex,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "block": block, "kind": kind, "text": text.strip(),
        "source_url": url, "evidence_status": evidence, "prev_sha256": previous,
    }
    event["sha256"] = _digest(event)
    state["events"].append(event)
    _write(path, state, stopped=studio._stop_event.is_set)
    return {"status": "SAVED_LOCAL_NOT_E11", "project_id": request["project_id"],
            "event_id": event["event_id"], "sha256": event["sha256"],
            "evidence_status": evidence}


def _export_project(studio, path, project_id):
    """Concrete local Markdown document; never publication, payment or upload."""
    state=_read(path)
    if not state["events"]:raise ValueError("CS5_EXPORT_EMPTY_HOLD")
    if studio._stop_event.is_set():raise ValueError("CS5_STOP_ACTIVE")
    destination=path.parent/"cs5_project_export.md"
    if destination.is_symlink() or path.parent.is_symlink():raise ValueError("CS5_EXPORT_PATH_HOLD")
    lines=["# NOX HELION Creative · "+project_id,"",
           "Local user-authored notes. Revenue claims and external citations are NOT verified.",""]
    for event in state["events"]:
        lines.extend(["## "+event["block"]+" / "+event["kind"],"",
                      event["text"].replace("<","&lt;").replace(">","&gt;"),"",
                      "Timestamp: "+str(event.get("created_at_utc","unknown")),
                      "Evidence: "+str(event.get("evidence_status","LOCAL_RECORD_ONLY")),
                      "Source: "+str(event.get("source_url","")),
                      "SHA256: "+event["sha256"],""])
    data=("\n".join(lines)+"\n").encode("utf-8")
    if len(data)>2_000_000:raise ValueError("CS5_EXPORT_SIZE_HOLD")
    fd,temp=tempfile.mkstemp(prefix=".cs5-export-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        if studio._stop_event.is_set():raise ValueError("CS5_STOP_ACTIVE")
        if destination.is_symlink():raise ValueError("CS5_EXPORT_PATH_HOLD")
        os.replace(temp,destination)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {"status":"EXPORTED_LOCAL_NOT_PUBLISHED","project_id":project_id,
            "file":"projects/"+project_id+"/cs5_project_export.md",
            "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
            "events":len(state["events"])}
