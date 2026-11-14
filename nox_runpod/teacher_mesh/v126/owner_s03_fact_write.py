"""NOX V126: owner-confirmed WEB V29 facts in ORIGINAL S03 M2.

Never a second DB. Delegates writes to the native original S03 'remember'
function, verifies committed row by exact content SHA, provenance, and
JSON metadata. No inferred fact verification, no arbitrary PC commands.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse

OWNER = "nox-single-owner"
_MAX_CONTENT = 5000
_FACT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_OWNER_ATTESTED = "OWNER_ATTESTED_NOT_INDEPENDENTLY_VERIFIED"


def _connect():
    import s03_memory
    path = Path(s03_memory.DB)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("HOLD_ORIGINAL_S03_FILE")
    con=sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=4)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _find(key):
    """Read only, bounded by key appearance. No FTS or new index required."""
    rows=[]
    with _connect() as db:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise RuntimeError("HOLD_ORIGINAL_S03_INTEGRITY")
        cols={r[1] for r in db.execute("PRAGMA table_info(s03_items)")}
        if not {"id","text","segment","sha256","provenance","meta"}.issubset(cols):
            raise RuntimeError("HOLD_ORIGINAL_S03_SCHEMA")
        for r in db.execute(
            "SELECT id,text,sha256,provenance,meta FROM s03_items "
            "WHERE segment='M2' AND instr(meta,?)>0 "
            "ORDER BY ts DESC LIMIT 75", (key,)):
            try:
                meta=json.loads(r["meta"] or "{}")
            except (TypeError,ValueError):
                continue
            if not isinstance(meta,dict) or meta.get("fact_key")!=key or meta.get("owner")!=OWNER:
                continue
            rows.append((r,meta))
    return rows


def _validate(data):
    if not isinstance(data,dict):
        raise ValueError("INVALID_BODY")
    key=data.get("fact_key")
    if not isinstance(key,str) or not _FACT_KEY.fullmatch(key):
        raise ValueError("INVALID_FACT_KEY")
    content=data.get("content")
    if not isinstance(content,str) or not content.strip() or len(content)>_MAX_CONTENT:
        raise ValueError("INVALID_CONTENT")
    if content!=content.strip() or len(content.encode("utf-8"))>20000:
        raise ValueError("CONTENT_NOT_CANONICAL")
    digest=hashlib.sha256(content.encode("utf-8")).hexdigest()
    supplied=data.get("source_sha256")
    if not isinstance(supplied,str) or not _SHA.fullmatch(supplied) or supplied!=digest:
        raise ValueError("SOURCE_SHA_MISMATCH")
    ref=data.get("source_ref")
    if (not isinstance(ref,str) or not ref.strip() or ref!=ref.strip()
            or len(ref)>250 or any(ord(c)<32 for c in ref)):
        raise ValueError("INVALID_PROVENANCE")
    start=data.get("valid_from")
    if not isinstance(start,str) or len(start)>45:
        raise ValueError("INVALID_VALID_FROM")
    try:
        stamp=datetime.fromisoformat(start.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_VALID_FROM") from exc
    if stamp.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    # Do not let future dates be represented as already verified observations.
    if stamp.astimezone(timezone.utc)>datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=1):
        raise ValueError("FUTURE_VALID_FROM")
    return {"fact_key":key,"content":content,"source_sha256":digest,
            "source_ref":ref,"valid_from":stamp.astimezone(timezone.utc).isoformat()}


def _persist(payload):
    key=payload["fact_key"]
    existing=_find(key)
    if existing:
        for row,meta in existing:
            if (row["sha256"]==payload["source_sha256"] and
                    row["text"]==payload["content"] and
                    row["provenance"]==payload["source_ref"]):
                return {"status":"COMMITTED","id":str(row["id"])[:120],
                        "event_id":str(row["id"])[:120],"fact_key":key,
                        "source_sha256":payload["source_sha256"],
                        "source_ref":payload["source_ref"],
                        "source":"ORIGINAL_NATIVE_S03_M2","idempotent":True,
                        "evidence_status":_OWNER_ATTESTED}
        raise RuntimeError("HOLD_FACT_KEY_CONFLICT")
    meta={"fact_key":key,"valid_from":payload["valid_from"],
          "source_ref":payload["source_ref"],"source_sha256":payload["source_sha256"],
          "owner":OWNER,"origin":"NOX_WEB_V29_OWNER_CONFIRMED",
          "evidence_status":_OWNER_ATTESTED}
    import s03_memory
    if not callable(getattr(s03_memory,"remember",None)):
        raise RuntimeError("HOLD_ORIGINAL_WRITER_MISSING")
    # The ORIGINAL implementation atomically writes its own S03 transaction.
    s03_memory.remember(text=payload["content"],segment="M2",
                        provenance=payload["source_ref"],salience=.65,meta=meta)
    found=_find(key)
    for row,check in found:
        if (row["sha256"]==payload["source_sha256"] and
                row["text"]==payload["content"] and
                row["provenance"]==payload["source_ref"] and
                check.get("source_sha256")==payload["source_sha256"]):
            ident=str(row["id"])[:120]
            return {"status":"COMMITTED","id":ident,"event_id":ident,
                    "fact_key":key,"source_sha256":payload["source_sha256"],
                    "source_ref":payload["source_ref"],
                    "source":"ORIGINAL_NATIVE_S03_M2",
                    "idempotent":False,"evidence_status":_OWNER_ATTESTED}
    raise RuntimeError("HOLD_NATIVE_S03_COMMIT_READBACK")


def register_nox_v126_owner_facts(app,trusted):
    check=trusted.get("_session_ok")
    unauthorized=trusted.get("_unauthorized")
    if not callable(check) or not callable(unauthorized):
        raise RuntimeError("HOLD_EXISTING_OWNER_AUTH")
    if any(getattr(x,"path","")=="/api/nox/memory/facts" for x in app.routes):
        raise RuntimeError("HOLD_OWNER_FACT_ROUTE_CONFLICT")
    gate=asyncio.Lock()
    @app.post("/api/nox/memory/facts")
    async def save_owner_confirmed_fact(request:Request):
        if not check(request):
            return unauthorized()
        if request.headers.get("content-type","").split(";")[0].lower()!="application/json":
            return JSONResponse({"error":"JSON_REQUIRED"},status_code=415)
        if request.headers.get("content-length","").isdigit() and int(request.headers["content-length"])>23000:
            return JSONResponse({"error":"FACT_TOO_LARGE"},status_code=413)
        try:
            wire=await request.body()
            if len(wire)>23000:
                return JSONResponse({"error":"FACT_TOO_LARGE"},status_code=413)
            data=_validate(json.loads(wire))
        except (TypeError,ValueError,json.JSONDecodeError) as exc:
            return JSONResponse({"error":str(exc)[:75]},status_code=422)
        async with gate:
            try:
                result=await asyncio.wait_for(asyncio.to_thread(_persist,data),timeout=12)
                return JSONResponse(result,headers={"Cache-Control":"no-store"})
            except Exception as exc:
                reason=str(exc)
                reason=reason if reason.startswith("HOLD_") and len(reason)<90 else "HOLD_NATIVE_FACT_WRITE"
                return JSONResponse({"status":"HOLD","reason":reason},status_code=503,
                                    headers={"Cache-Control":"no-store"})
