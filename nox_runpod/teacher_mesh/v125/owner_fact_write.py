"""V125 owner-only POST /api/nox/memory/facts on ORIGINAL NOX S03.

No new database, no model, scheduler, backend or mock records. The existing
s03_memory.remember() performs the durable write. Responses say SAVED ONLY
after an exact native SQLite readback. Cannot assert truth of user-supplied fact.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

_MAX_BODY = 17000
_MAX_TEXT = 5000
_HEX = re.compile(r"^[0-9a-f]{64}$")
_FACT_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_STOP_PATHS = (
    "/root/nox/STOP", "/root/nox/STOP.flag",
    "/root/nox/stop.flag", "/root/nox/.stop",
    "/workspace/NOX_STOP", "/root/nox/program/STOP",
)


def _stopped() -> bool:
    return any(Path(p).exists() for p in _STOP_PATHS)


def _native_db():
    import s03_memory
    root = Path(s03_memory.DB)
    if not root.is_file() or root.is_symlink():
        raise RuntimeError("HOLD_ORIGINAL_S03_MISSING")
    con = sqlite3.connect("file:" + str(root) + "?mode=ro",
                          uri=True, timeout=4)
    con.execute("PRAGMA query_only=ON")
    con.row_factory = sqlite3.Row
    return con


def _validate(body: object) -> dict:
    if not isinstance(body, dict):
        raise ValueError("INVALID_FACT_PAYLOAD")
    key = body.get("fact_key")
    content = body.get("content")
    source = body.get("source_ref")
    supplied = body.get("source_sha256")
    valid_from = body.get("valid_from")
    if not isinstance(key, str) or not _FACT_KEY.fullmatch(key.strip()):
        raise ValueError("INVALID_FACT_KEY")
    if not isinstance(content, str) or not content.strip() or len(content) > _MAX_TEXT:
        raise ValueError("INVALID_FACT_CONTENT")
    if len(content.encode("utf8")) > 14000:
        raise ValueError("INVALID_FACT_BYTES")
    if not isinstance(source, str) or not source.strip() or len(source) > 250:
        raise ValueError("INVALID_SOURCE_REFERENCE")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in source):
        raise ValueError("INVALID_SOURCE_CONTROL")
    if not isinstance(supplied, str) or not _HEX.fullmatch(supplied):
        raise ValueError("INVALID_SOURCE_SHA256")
    calculated = hashlib.sha256(content.encode("utf8")).hexdigest()
    if supplied != calculated:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    if not isinstance(valid_from, str) or not 10 <= len(valid_from) <= 40:
        raise ValueError("INVALID_FACT_TIMESTAMP")
    try:
        moment = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError("INVALID_FACT_TIMESTAMP") from None
    return {"fact_key": key.strip(), "content": content,
            "source_ref": source.strip(), "source_sha256": supplied,
            "valid_from": valid_from}


def _provenance(key: str, source: str) -> tuple[str, str]:
    # V120 existing facts/history searches text and provenance literally.
    # A validated literal key is searchable; a base64-only key is not.
    prefix = "owner-fact:" + key + "|"
    return prefix, prefix + source


def _read_existing(db, prefix: str, text: str, provenance: str):
    cols = {row[1] for row in db.execute("PRAGMA table_info(s03_items)")}
    if not {"id","segment","text","provenance","ts"}.issubset(cols):
        raise RuntimeError("HOLD_NATIVE_S03_SCHEMA")
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("HOLD_S03_INTEGRITY")
    previous = db.execute(
        "SELECT id, text, provenance FROM s03_items "
        "WHERE segment='M2' AND substr(provenance,1,?)=? "
        "ORDER BY ts DESC LIMIT 50", (len(prefix),prefix)).fetchall()
    duplicates = [row for row in previous
                  if row["text"] == text and row["provenance"] == provenance]
    return previous, duplicates[0]["id"] if duplicates else None


def _commit_fact(note: dict) -> dict:
    import s03_memory
    if _stopped():
        raise RuntimeError("HOLD_STOP")
    prefix, provenance = _provenance(note["fact_key"], note["source_ref"])
    with _native_db() as db:
        previous, duplicate_id = _read_existing(db, prefix, note["content"], provenance)
        if duplicate_id is not None:
            return {"event_id": str(duplicate_id), "duplicate": True,
                    "supersedes": None}
        previous_id = str(previous[0]["id"]) if previous else None
    if _stopped():
        raise RuntimeError("HOLD_STOP_BEFORE_NATIVE_SAVE")
    s03_memory.remember(
        note["content"], segment="M2", provenance=provenance,
        salience=0.8,
        meta={"source": "OWNER_CONFIRMED_NOTE",
              "fact_key": note["fact_key"],
              "source_ref": note["source_ref"],
              "source_sha256": note["source_sha256"],
              "valid_from": note["valid_from"],
              "supersedes": previous_id,
              "owner_confirmed": True,
              "neural_weights_changed": False})
    with _native_db() as db:
        _prior, verified = _read_existing(db, prefix, note["content"], provenance)
    if verified is None:
        raise RuntimeError("HOLD_S03_NATIVE_SAVE_NOT_READ_BACK")
    return {"event_id": str(verified), "duplicate": False,
            "supersedes": previous_id}


def register_nox_v125_owner_fact_write(app, trusted: dict) -> None:
    auth = trusted.get("_session_ok")
    reject = trusted.get("_unauthorized")
    if not callable(auth) or not callable(reject):
        raise RuntimeError("HOLD_NATIVE_OWNER_AUTH_UNAVAILABLE")
    path = "/api/nox/memory/facts"
    if any(getattr(route, "path", "") == path for route in app.routes):
        raise RuntimeError("HOLD_EXISTING_FACT_ROUTE_CONFLICT")
    gate = asyncio.Lock()

    @app.post(path)
    async def owner_confirmed_fact(request: Request):
        if not auth(request):
            return reject()
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                size = _MAX_BODY + 1
            if size < 0 or size > _MAX_BODY:
                return JSONResponse({"error":"FACT_BODY_TOO_LARGE"},status_code=413)
        raw = await request.body()
        if len(raw) > _MAX_BODY:
            return JSONResponse({"error":"FACT_BODY_TOO_LARGE"},status_code=413)
        try:
            note = _validate(json.loads(raw))
        except (ValueError, UnicodeDecodeError, TypeError) as error:
            reason = str(error)
            return JSONResponse({"error": reason if reason.startswith(("INVALID_","SOURCE_SHA256_MISMATCH"))
                                 else "INVALID_FACT_JSON"},status_code=422)
        if _stopped():
            return JSONResponse({"status":"HOLD","reason":"HOLD_STOP"},status_code=409)
        async with gate:
            try:
                proof = await asyncio.to_thread(_commit_fact, note)
            except Exception as error:
                reason = str(error)
                return JSONResponse(
                    {"status":"HOLD","reason":reason if reason.startswith("HOLD_")
                     and len(reason)<120 else "HOLD_NATIVE_S03_WRITE"},status_code=503)
        return JSONResponse(
            {"status":"SAVED","source":"EXISTING_NOX_S03_M2",
             "event_id":proof["event_id"],"id":proof["event_id"],
             "fact_key":note["fact_key"],"source_sha256":note["source_sha256"],
             "deduplicated":proof["duplicate"],"supersedes":proof["supersedes"],
             "saved":True,"s03_integrated":True,
             "neural_weights_changed":False},
            headers={"Cache-Control":"no-store"})
