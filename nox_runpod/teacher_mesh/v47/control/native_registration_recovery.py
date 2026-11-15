"""Reconcile a partially accepted V175 job in the EXISTING OneHost/S03.

This module never spawns a worker, GPU trainer, model, service or database.
It only uses trusted owner-native callbacks already bound to the ONE host.
An uncertain prior enqueue MUST NOT lead to another queue_enqueue.
"""
from __future__ import annotations
from collections.abc import Mapping
from hashlib import sha256
import json
import re

ID = re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
SHA = re.compile(r"^[a-f0-9]{64}$")


def _hash(row):
    return sha256(json.dumps(row,sort_keys=True,separators=(",",":"),
                            ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def reconcile_existing_registration(native, *, owner_scope:str, task_id:str,
                                     matrix_sha256:str, legacy_task_id:str|None=None,
                                     inventory:Mapping)->dict:
    """Read one old native job and its S03 proof; repair only a missing S03 event.

    S03 lookup must independently bind an event to exact task/job/scope/SHA.
    If an existing job is observed without a verifiable S03 event, fail closed
    unless an explicit owner-signed audit append is approved and read back.
    """
    base={"performed":False,"new_queue_jobs":0,"task_id":task_id}
    ids=(task_id,legacy_task_id) if legacy_task_id else (task_id,)
    if (not all(isinstance(x,str) and ID.fullmatch(x) for x in ids)
            or not isinstance(owner_scope,str) or not ID.fullmatch(owner_scope)
            or not isinstance(matrix_sha256,str) or SHA.fullmatch(matrix_sha256) is None):
        return {**base,"state":"HOLD_REGISTRATION_ID_OR_SHA"}
    if (not isinstance(inventory,Mapping)
            or inventory.get("owner_queue_writer_lease_verified") is not True
            or inventory.get("native_queue_verified") is not True
            or inventory.get("native_writes_available") is not True):
        return {**base,"state":"HOLD_OWNER_QUEUE_LEASE"}
    ports=("stop","authorize","state","native_task_status","queue_readback",
           "s03_registration_lookup","approve","s03_audit","s03_verify")
    if any(not callable(getattr(native,key,None)) for key in ports):
        return {**base,"state":"HOLD_REGISTRATION_NATIVE_PORTS"}
    def owner_gate():
        try:
            return native.stop() is False and native.authorize(owner_scope) is True
        except Exception:
            return False
    if not owner_gate():
        return {**base,"state":"HOLD_REGISTRATION_OWNER_OR_STOP"}
    try:
        found=[]
        for identity in ids:
            value=native.native_task_status(identity)
            if value is None:
                continue
            if (not isinstance(value,Mapping) or value.get("task_id")!=identity
                    or value.get("native_verified") is not True
                    or value.get("owner_scope")!=owner_scope
                    or not isinstance(value.get("job_id"),str)
                    or not ID.fullmatch(value["job_id"])
                    or value.get("state") not in ("PENDING","RUNNING","CLAIMED")
                    or not isinstance(value.get("receipt_sha256"),str)
                    or SHA.fullmatch(value["receipt_sha256"]) is None):
                return {**base,"state":"HOLD_EXISTING_NATIVE_REGISTRATION_UNTRUSTED"}
            found.append(value)
        if not found or len({r["job_id"] for r in found})!=1:
            return {**base,"state":"HOLD_EXISTING_JOB_MISSING_OR_AMBIGUOUS"}
        # All identities must point to the SAME owned queue job; never
        # treat alias identities as independent jobs.
        item=found[0]
        jid=item["job_id"]
        readback=native.queue_readback(jid)
        if (not isinstance(readback,Mapping) or readback.get("job_id")!=jid
                or readback.get("task_id") not in ids
                or readback.get("state") not in ("pending","running")):
            return {**base,"state":"HOLD_EXISTING_NATIVE_QUEUE_READBACK"}
        event={"schema":"NOX_V175_EXISTING_REGISTRATION_S03_RECONCILE_V1",
               "task_id":task_id,"legacy_task_id":legacy_task_id,
               "job_id":jid,"owner_scope":owner_scope,
               "native_registry_receipt_sha256":item["receipt_sha256"],
               "source_matrix_sha256":matrix_sha256}
        event_sha=_hash(event)
        def lookup():
            row=native.s03_registration_lookup(event)
            if not isinstance(row,Mapping):
                return "HOLD"
            if row.get("state")=="MISSING" and row.get("native_verified") is True:
                return "MISSING"
            if (row.get("state")=="PRESENT"
                    and row.get("native_verified") is True
                    and row.get("event_sha256")==event_sha
                    and row.get("job_id")==jid
                    and row.get("owner_scope")==owner_scope):
                return "PRESENT"
            return "HOLD"
        observed=lookup()
        if observed=="PRESENT":
            return {**base,"state":"EXISTING_JOB_AND_S03_VERIFIED",
                    "job_id":jid,"s03_receipt_sha256":event_sha}
        if observed!="MISSING":
            return {**base,"state":"HOLD_EXISTING_S03_PROVENANCE"}
        # A missing S03 receipt is a repairable *metadata* gap, not
        # permission to re-enqueue / restart an already running job.
        # Owner approval may revoke/rotate its OneHost writer lease. A caller's
        # initial inventory cannot authorize a later S03 repair. Compare native
        # fencing tokens both before and AFTER approval; native S03 must also
        # enforce the lease atomically at its own append boundary.
        def current_lease(previous):
            snap=native.state()
            if (not isinstance(snap,Mapping)
                    or snap.get("native_queue_verified") is not True
                    or snap.get("owner_queue_writer_lease_verified") is not True
                    or snap.get("native_writes_available") is not True
                    or snap.get("stop_active") is not False
                    or not isinstance(snap.get("task_status"),Mapping)
                    or type(snap.get("now_unix")) is not int
                    or snap["now_unix"]<=0):
                return None
            fence=("owner_queue_writer_lease_id","owner_queue_writer_lease_epoch",
                   "queue_epoch","owner_scope")
            if any(snap.get(key)!=previous.get(key)
                   for key in fence if key in snap or key in previous):
                return None
            return snap
        before=current_lease(inventory)
        if before is None:
            return {**base,"state":"HOLD_S03_REPAIR_LEASE_CHANGED_BEFORE_APPROVAL"}
        if not owner_gate() or native.approve(owner_scope,event_sha,dict(before)) is not True:
            return {**base,"state":"HOLD_S03_REPAIR_NOT_APPROVED"}
        if not owner_gate():
            return {**base,"state":"HOLD_S03_REPAIR_STOP_RACE"}
        after=current_lease(before)
        if after is None:
            return {**base,"state":"HOLD_S03_REPAIR_LEASE_CHANGED_AFTER_APPROVAL"}
        # Approval must still refer to the same original queue job, not a new
        # task/status that raced with the S03 repair. Never re-enqueue it.
        latest=native.native_task_status(task_id)
        again=native.queue_readback(jid)
        if (not isinstance(latest,Mapping) or latest.get("task_id")!=task_id
                or latest.get("job_id")!=jid
                or latest.get("owner_scope")!=owner_scope
                or latest.get("native_verified") is not True
                or latest.get("receipt_sha256")!=item["receipt_sha256"]
                or latest.get("state") not in ("PENDING","RUNNING","CLAIMED")
                or not isinstance(again,Mapping) or again.get("job_id")!=jid
                or again.get("task_id") not in ids
                or again.get("state") not in ("pending","running")):
            return {**base,"state":"HOLD_S03_REPAIR_NATIVE_JOB_CHANGED"}
        proof=native.s03_audit(event)
        if native.s03_verify(proof,event) is not True:
            return {**base,"state":"HOLD_S03_REPAIR_READBACK","performed":"UNKNOWN"}
        if lookup()!="PRESENT":
            return {**base,"state":"HOLD_S03_REPAIR_INDEPENDENT_PROOF","performed":"UNKNOWN"}
        return {**base,"state":"ORPHANED_NATIVE_S03_RECEIPT_RECOVERED",
                "performed":True,"job_id":jid,"s03_receipt_sha256":event_sha}
    except Exception:
        # Any exception may have occurred *after* S03 append. Never erase
        # the record, blindly retry, or report zero native effects.
        return {**base,"state":"HOLD_EXISTING_REGISTRATION_NATIVE_EXCEPTION",
                "performed":"UNKNOWN"}
