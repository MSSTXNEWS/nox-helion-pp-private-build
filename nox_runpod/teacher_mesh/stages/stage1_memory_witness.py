#!/usr/bin/env python3
"""NOX V28 Stage 1: read-only S03 autobiography witness for EXISTING OneHost.

Existing trusted OneHost supplies authenticated S03 callbacks and boot ID.
No new backend, SQLite store, S03 write, LLM prompt masquerading as a fact,
or claiming a real Windows restart from a synthetic unittest.
"""
from __future__ import annotations
from hashlib import sha256
from typing import Any
import json
import re

SCHEMA="nox-v28-stage1-s03-recall-witness-v1"
HEXDIGEST=re.compile(r"^[a-f0-9]{64}$")
EVENT_ID=re.compile(r"^[A-Za-z0-9_.:-]{3,128}$")
SCOPE_ID=re.compile(r"^[A-Za-z0-9_-]{1,64}$")
QUESTION="Ты кого съел?"
NO_PRIVACY_TEXT_IN_WITNESS=True

def _hold(reason:str):
    return {"schema":SCHEMA,"state":"HOLD","reason":reason,
            "live_s03_verified":False,"windows_reboot_verified":False}

def capture_recall(overlay:Any, *,scope:str,expected_event_id:str,boot_id:str,
                   authenticated_onehost:bool)->dict:
    """Produce a source-attested hash of a verified M7 event from actual bound S03.

    The caller MUST verify its own authenticated OneHost session. The model is
    not allowed to supply scope/event ID/boot ID or privileged approval.
    """
    if authenticated_onehost is not True:
        return _hold("AUTHENTICATED_ONEHOST_REQUIRED")
    if (not isinstance(scope,str) or not SCOPE_ID.fullmatch(scope)
        or not isinstance(expected_event_id,str) or not EVENT_ID.fullmatch(expected_event_id)
        or not isinstance(boot_id,str) or not HEXDIGEST.fullmatch(boot_id)):
        return _hold("INVALID_NATIVE_SCOPE_OR_BOOT_EVIDENCE")
    if not callable(getattr(overlay,"prepare",None)):
        return _hold("LIVE_S03_OVERLAY_NOT_BOUND")
    try:
        result=overlay.prepare(QUESTION,scope=scope,language="ru")
    except Exception:
        return _hold("S03_CALLBACK_FAILURE")
    if not isinstance(result,dict) or result.get("state")!="PREPARED":
        return _hold("S03_NOT_PREPARED")
    records=result.get("memories")
    if not isinstance(records,list):
        return _hold("S03_MEMORY_FORMAT")
    matches=[r for r in records if (isinstance(r,dict) and
         r.get("id")==expected_event_id and r.get("segment")=="M7" and
         isinstance(r.get("source_uri"),str) and
         r["source_uri"].startswith(("s03://","nox-checkpoint://","github://")) and
         isinstance(r.get("text"),str) and r["text"].strip())]
    if len(matches)!=1:
        return _hold("VERIFIED_GENESIS_EVENT_NOT_RETRIEVED")
    record=matches[0]
    # Avoid leaking full private autobiographical text into CI or Drive.
    payload=json.dumps({"id":record["id"],"text":record["text"],
                        "source_uri":record["source_uri"],
                        "timestamp_utc":record.get("timestamp_utc")},
                       sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return {
      "schema":SCHEMA,"state":"S03_VERIFIED_EVENT_READABLE_SOURCE_ONLY",
      "scope":scope,"boot_id":boot_id,
      "event_id":expected_event_id,"event_fingerprint_sha256":sha256(payload.encode("utf-8")).hexdigest(),
      "memory_segment":"M7",
      "autobiography_question":"teacher_distillation_and_provenance",
      "memory_event_verified_by_overlay":True,
      "evidence_contains_raw_private_text":False,
      "live_s03_verified":False,
      "windows_reboot_verified":False,
      "qualification":"CALLBACK_EVIDENCE_ONLY; independent live OneHost readback and signed reboot receipt required",
      "source_uri_scheme":record["source_uri"].split("://",1)[0],
    }

def compare_recall(before:dict,after:dict,*,reboot:dict|None=None)->dict:
    """Deterministic parity. This NEVER silently upgrades a synthetic reboot."""
    if any(not isinstance(x,dict) or x.get("schema")!=SCHEMA or
           x.get("state")!="S03_VERIFIED_EVENT_READABLE_SOURCE_ONLY"
           for x in (before,after)):
        return _hold("NEEDS_TWO_VERIFIED_READS")
    if before.get("scope")!=after.get("scope") or before.get("event_id")!=after.get("event_id"):
        return _hold("SCOPE_OR_EVENT_CHANGED")
    if before.get("event_fingerprint_sha256")!=after.get("event_fingerprint_sha256"):
        return _hold("RECALL_FACT_CHANGED_OR_MISSING")
    if before.get("boot_id")==after.get("boot_id"):
        return _hold("NO_BOOT_BOUNDARY_EVIDENCE")
    if (not isinstance(reboot,dict) or reboot.get("verified_by_existing_onehost") is not True
        or reboot.get("before_boot_id")!=before.get("boot_id")
        or reboot.get("after_boot_id")!=after.get("boot_id")
        or reboot.get("native_restart_readback") is not True):
        return _hold("REAL_WINDOWS_REBOOT_RECEIPT_REQUIRED")
    return {
        "schema":SCHEMA,
        "state":"NATIVE_REBOOT_RECEIPT_CLAIMS_STABLE_S03_RECALL",
        "event_id":before["event_id"],"scope":before["scope"],
        "event_fingerprint_sha256":before["event_fingerprint_sha256"],
        "before_boot_id":before["boot_id"],"after_boot_id":after["boot_id"],
        "live_s03_verified":False,
        "windows_reboot_verified":False,
        "independent_e07_required":True,
        "limitation":"Trusts host-supplied signed reboot evidence; has not independently reproduced on Windows",
    }
