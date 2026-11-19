"""NOX 1B: read-only, source-level reconciliation of original V47 receipts.

No networking, credentials, queue writes, scheduling or native PASS. This checks
internal coherence of already supplied observations; OneHost must independently
attest that the callbacks came from instance 60509551 with owner authorization.
Run: python 1B_queue_audit.py --selftest
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
import re
import sys
import unittest

INSTANCE_ID = 60509551
JOB = re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TASK = re.compile(r"^(?:NOX-V46-(?:0[1-9]|[1-5][0-9]|60)|R60-(?:00[1-9]|0[1-5][0-9]|060))$")
RUNNING = {"RUNNING", "PENDING", "CLAIMED"}


def digest(value: Mapping) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def reconcile(*, statuses, queues, events, s03, owner_scope, source_sha256,
              instance_id=INSTANCE_ID, now_unix=None, heartbeat_s=600,
              stop_active=False):
    """Cross-check original V47-shaped evidence, never authorize a native action.

    statuses: task_id -> native_task_status response
    queues: job_id -> queue_readback response
    events: job_id -> original queued receipt event (NO payloads or memory text)
    s03: job_id -> s03_registration_lookup response
    This function NEVER treats self-reported 'native_verified' as a signature.
    """
    out = {"schema": "NOX_1B_ORIGINAL_QUEUE_S03_CROSSCHECK_V1",
           "state": "HOLD_SOURCE_CROSSCHECK_NOT_NATIVE_ATTESTATION",
           "status_job_ids_seen": 0, "crosschecked_queue_s03_pairs": 0,
           "rejected": [], "stale_heartbeat_holds": [],
           "native_actual_job_count": "UNKNOWN_NOT_OWNER_SIGNED",
           "native_jobs_started": 0, "retry_permitted": False,
           "stop_permitted": False, "native_pass": False}
    if (instance_id != INSTANCE_ID or not isinstance(owner_scope, str)
            or not 4 <= len(owner_scope) <= 128
            or not SHA.fullmatch(str(source_sha256))
            or not all(isinstance(x, Mapping) for x in (statuses, queues, events, s03))
            or now_unix is not None and (type(now_unix) is not int or now_unix <= 0)
            or type(heartbeat_s) is not int or not 60 <= heartbeat_s <= 3600):
        out["state"] = "HOLD_INVALID_EVIDENCE_ENVELOPE"
        return out
    if stop_active is not False:
        out["state"] = "HOLD_STOP_LATCH"
        return out
    # Pre-count IDs: a later collision invalidates BOTH rows, not just the second.
    collisions = {}
    for item in statuses.values():
        if isinstance(item, Mapping) and isinstance(item.get("job_id"), str):
            jid = item["job_id"]
            collisions[jid] = collisions.get(jid, 0) + 1
    # The original V47 audit rejects foreign task IDs as an entire batch.
    # Do the same before sorting: mixed string/non-string keys otherwise raise
    # TypeError, and a partial audit must not be promoted as valid evidence.
    if any(not isinstance(tid, str) or not TASK.fullmatch(tid)
           for tid in statuses):
        out["state"] = "HOLD_FOREIGN_TASK_IDS"
        return out
    # V46 and R60 are alternate names for the SAME 60 logical tasks.
    # The original V175 supervisor rejects mixed families. Otherwise one
    # canonical task with two different native job IDs can count twice here.
    if len({("R60" if tid.startswith("R60-") else "V46")
            for tid in statuses}) > 1:
        out["state"] = "HOLD_MIXED_TASK_FAMILIES"
        return out
    for tid, status in sorted(statuses.items()):
        if (not isinstance(tid, str) or not TASK.fullmatch(tid)
                or not isinstance(status, Mapping)):
            out["rejected"].append({"task_id": str(tid), "reason": "BAD_STATUS"})
            continue
        jid = status.get("job_id")
        if (not isinstance(jid, str) or not JOB.fullmatch(jid)
                or status.get("task_id") != tid
                or status.get("owner_scope") != owner_scope
                or status.get("instance_id", instance_id) != instance_id
                or status.get("native_verified") is not True
                or not SHA.fullmatch(str(status.get("receipt_sha256", "")))):
            out["rejected"].append({"task_id": tid, "reason": "UNTRUSTED_STATUS"})
            continue
        out["status_job_ids_seen"] += 1
        if collisions.get(jid, 0) != 1:
            out["rejected"].append({"task_id": tid, "reason": "DUPLICATE_JOB_ID"})
            continue
        # A registration receipt is not proof of an active job when the
        # native status has already become terminal or disagrees with queue.
        native_state = status.get("state")
        # Native callbacks may return malformed JSON values such as [] or {}.
        # Validate type before membership in a set (unhashable values must HOLD).
        if not isinstance(native_state, str) or native_state not in RUNNING:
            out["rejected"].append({"task_id": tid, "reason": "NOT_ACTIVE_NATIVE_STATE"})
            continue
        queue, event, proof = queues.get(jid), events.get(jid), s03.get(jid)
        if (not isinstance(queue, Mapping) or queue.get("job_id") != jid
                or queue.get("task_id") != tid
                or queue.get("owner_scope", owner_scope) != owner_scope
                or queue.get("instance_id", instance_id) != instance_id
                or queue.get("state") not in ("pending", "running")):
            out["rejected"].append({"task_id": tid, "reason": "QUEUE_READBACK_MISSING_OR_MISMATCH"})
            continue
        if (native_state == "RUNNING" and queue.get("state") != "running"
                or native_state == "PENDING" and queue.get("state") != "pending"):
            out["rejected"].append({"task_id": tid, "reason": "QUEUE_STATUS_STATE_MISMATCH"})
            continue
        if (not isinstance(event, Mapping) or event.get("schema") != "NOX_V46_QUEUED_RECEIPT"
                or event.get("job_id") != jid or event.get("task_id") != tid
                or event.get("owner_scope") != owner_scope
                or event.get("instance_id", instance_id) != instance_id
                or event.get("state") != queue.get("state")
                or event.get("source_matrix_sha256") != source_sha256
                or event.get("native_task_status_receipt_sha256") != status.get("receipt_sha256")
                or not all(SHA.fullmatch(str(event.get(k, ""))) for k in
                           ("job_sha256", "native_queue_receipt_sha256"))):
            out["rejected"].append({"task_id": tid, "reason": "ORIGINAL_EVENT_MISMATCH"})
            continue
        # Supplied queue events can be malformed; refuse them without crashing.
        try:
            expected_event_sha256 = digest(event)
        except (TypeError, ValueError, OverflowError):
            out["rejected"].append({"task_id": tid, "reason": "UNSERIALIZABLE_OR_NONFINITE_EVENT"})
            continue
        if (not isinstance(proof, Mapping) or proof.get("state") != "PRESENT"
                or proof.get("native_verified") is not True
                or proof.get("owner_scope") != owner_scope
                or proof.get("instance_id", instance_id) != instance_id
                or proof.get("task_id", tid) != tid
                or proof.get("job_id") != jid
                or proof.get("event_sha256") != expected_event_sha256):
            out["rejected"].append({"task_id": tid, "reason": "S03_DURABLE_READBACK_MISSING_OR_MISMATCH"})
            continue
        if native_state == "RUNNING":
            beat = status.get("heartbeat_unix")
            if (type(now_unix) is not int or type(beat) is not int
                    or beat <= 0 or beat > now_unix + 30 or now_unix - beat > heartbeat_s):
                out["stale_heartbeat_holds"].append(tid)
                out["rejected"].append({"task_id": tid, "reason": "HEARTBEAT_STALE_OR_UNKNOWN"})
                continue
        out["crosschecked_queue_s03_pairs"] += 1
    return out


def _example():
    h = "a" * 64
    tid, jid, owner = "NOX-V46-01", "native/001", "owner-verified"
    status = {"task_id": tid, "job_id": jid, "owner_scope": owner,
              "native_verified": True, "receipt_sha256": "b" * 64,
              "state": "PENDING"}
    queue = {"task_id": tid, "job_id": jid, "state": "pending"}
    event = {"schema": "NOX_V46_QUEUED_RECEIPT", "task_id": tid,
             "job_id": jid, "owner_scope": owner, "job_sha256": "c" * 64,
             "native_queue_receipt_sha256": "d" * 64,
             "native_task_status_receipt_sha256": "b" * 64,
             "state": "pending", "source_matrix_sha256": h}
    proof = {"state": "PRESENT", "native_verified": True,
             "owner_scope": owner, "job_id": jid, "event_sha256": digest(event)}
    return {"statuses": {tid: status}, "queues": {jid: queue},
            "events": {jid: event}, "s03": {jid: proof},
            "owner_scope": owner, "source_sha256": h, "now_unix": 2000}


class ContractTests(unittest.TestCase):
    def check(self, mutation=None, **kwargs):
        inp = _example()
        if mutation:
            mutation(inp)
        inp.update(kwargs)
        return reconcile(**inp)

    def test_crosscheck_never_native_pass(self):
        r = self.check()
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 1)
        self.assertFalse(r["native_pass"])
        self.assertEqual(r["native_actual_job_count"], "UNKNOWN_NOT_OWNER_SIGNED")

    def test_missing_s03(self):
        self.assertEqual(self.check(lambda d: d["s03"].clear())["crosschecked_queue_s03_pairs"], 0)

    def test_missing_queue(self):
        self.assertEqual(self.check(lambda d: d["queues"].clear())["crosschecked_queue_s03_pairs"], 0)

    def test_wrong_owner(self):
        self.assertEqual(self.check(lambda d: d["s03"]["native/001"].update(owner_scope="wrong"))["crosschecked_queue_s03_pairs"], 0)

    def test_wrong_event_digest(self):
        self.assertEqual(self.check(lambda d: d["s03"]["native/001"].update(event_sha256="f" * 64))["crosschecked_queue_s03_pairs"], 0)

    def test_status_only_never_counts(self):
        self.assertEqual(self.check(lambda d: (d["queues"].clear(),d["s03"].clear()))["status_job_ids_seen"], 1)

    def test_stop_latch(self):
        self.assertEqual(self.check(stop_active=True)["state"], "HOLD_STOP_LATCH")

    def test_other_instance(self):
        self.assertEqual(self.check(instance_id=123)["state"], "HOLD_INVALID_EVIDENCE_ENVELOPE")

    def test_stale_heartbeat(self):
        def mutation(d):
            d["statuses"]["NOX-V46-01"].update(state="RUNNING",heartbeat_unix=1000)
            d["queues"]["native/001"]["state"] = "running"
            d["events"]["native/001"]["state"] = "running"
            d["s03"]["native/001"]["event_sha256"] = digest(d["events"]["native/001"])
        self.assertEqual(len(self.check(mutation)["stale_heartbeat_holds"]), 1)

    def test_recent_heartbeat(self):
        def mutation(d):
            d["statuses"]["NOX-V46-01"].update(state="RUNNING",heartbeat_unix=1900)
            d["queues"]["native/001"]["state"] = "running"
            d["events"]["native/001"]["state"] = "running"
            d["s03"]["native/001"]["event_sha256"] = digest(d["events"]["native/001"])
        self.assertEqual(self.check(mutation)["crosschecked_queue_s03_pairs"], 1)

    def test_duplicate_job_id(self):
        def mutation(d):
            row = deepcopy(d["statuses"]["NOX-V46-01"])
            row["task_id"] = "NOX-V46-02"
            d["statuses"]["NOX-V46-02"] = row
        self.assertEqual(self.check(mutation)["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(self.check(mutation)["status_job_ids_seen"], 2)

    def test_unhashable_list_native_state_fails_closed(self):
        r = self.check(lambda d: d["statuses"]["NOX-V46-01"].update(state=[]))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "NOT_ACTIVE_NATIVE_STATE")
        self.assertFalse(r["native_pass"])

    def test_unhashable_mapping_native_state_fails_closed(self):
        r = self.check(lambda d: d["statuses"]["NOX-V46-01"].update(state={}))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "NOT_ACTIVE_NATIVE_STATE")
        self.assertFalse(r["native_pass"])

    def test_terminal_status_not_active_receipt(self):
        r = self.check(lambda d: d["statuses"]["NOX-V46-01"].update(state="FAILED"))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "NOT_ACTIVE_NATIVE_STATE")

    def test_running_status_pending_queue_mismatch(self):
        r = self.check(lambda d: d["statuses"]["NOX-V46-01"].update(
            state="RUNNING", heartbeat_unix=1900))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "QUEUE_STATUS_STATE_MISMATCH")

    def test_pending_status_running_queue_mismatch(self):
        def mismatch(d):
            d["queues"]["native/001"]["state"] = "running"
            d["events"]["native/001"]["state"] = "running"
            d["s03"]["native/001"]["event_sha256"] = digest(d["events"]["native/001"])
        r = self.check(mismatch)
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "QUEUE_STATUS_STATE_MISMATCH")

    def test_missing_job_id(self):
        self.assertEqual(self.check(lambda d: d["statuses"]["NOX-V46-01"].pop("job_id"))["crosschecked_queue_s03_pairs"], 0)

    def test_invalid_job_id(self):
        self.assertEqual(self.check(lambda d: d["statuses"]["NOX-V46-01"].update(job_id="bad id"))["crosschecked_queue_s03_pairs"], 0)

    def test_wrong_source_matrix(self):
        self.assertEqual(self.check(lambda d: d["events"]["native/001"].update(source_matrix_sha256="f"*64))["crosschecked_queue_s03_pairs"], 0)

    def test_foreign_owner_in_original_queue(self):
        r = self.check(lambda d: d["queues"]["native/001"].update(owner_scope="other-owner"))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_foreign_instance_in_original_queue(self):
        r = self.check(lambda d: d["queues"]["native/001"].update(instance_id=12345678))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_foreign_instance_in_native_status(self):
        r = self.check(lambda d: d["statuses"]["NOX-V46-01"].update(instance_id=12345678))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_foreign_task_in_original_s03_receipt(self):
        r = self.check(lambda d: d["s03"]["native/001"].update(task_id="NOX-V46-02"))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_foreign_instance_in_original_s03_receipt(self):
        r = self.check(lambda d: d["s03"]["native/001"].update(instance_id=12345678))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_matching_optional_cross_source_identity(self):
        def identity(d):
            d["statuses"]["NOX-V46-01"]["instance_id"] = INSTANCE_ID
            d["queues"]["native/001"].update(owner_scope=d["owner_scope"], instance_id=INSTANCE_ID)
            d["events"]["native/001"]["instance_id"] = INSTANCE_ID
            d["s03"]["native/001"].update(task_id="NOX-V46-01", instance_id=INSTANCE_ID,
                                            event_sha256=digest(d["events"]["native/001"]))
        self.assertEqual(self.check(identity)["crosschecked_queue_s03_pairs"], 1)

    def test_foreign_instance_in_original_event(self):
        def mismatch(d):
            d["events"]["native/001"]["instance_id"] = 12345678
            d["s03"]["native/001"]["event_sha256"] = digest(d["events"]["native/001"])
        self.assertEqual(self.check(mismatch)["crosschecked_queue_s03_pairs"], 0)

    def test_mixed_type_task_key_fail_closed(self):
        def mutation(d):
            d["statuses"][17] = d["statuses"]["NOX-V46-01"].copy()
        r = self.check(mutation)
        self.assertEqual(r["state"], "HOLD_FOREIGN_TASK_IDS")
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertFalse(r["native_pass"])

    def test_foreign_task_key_fail_closed(self):
        def mutation(d):
            d["statuses"]["OTHER-TASK-01"] = d["statuses"]["NOX-V46-01"].copy()
        r = self.check(mutation)
        self.assertEqual(r["state"], "HOLD_FOREIGN_TASK_IDS")
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)

    def test_unserializable_event_fail_closed(self):
        r = self.check(lambda d: d["events"]["native/001"].update(extraneous={3}))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "UNSERIALIZABLE_OR_NONFINITE_EVENT")
        self.assertFalse(r["native_pass"])

    def test_nonfinite_event_fail_closed(self):
        r = self.check(lambda d: d["events"]["native/001"].update(extraneous=float("nan")))
        self.assertEqual(r["crosschecked_queue_s03_pairs"], 0)
        self.assertEqual(r["rejected"][0]["reason"], "UNSERIALIZABLE_OR_NONFINITE_EVENT")
        self.assertFalse(r["native_pass"])

    def test_nonpositive_heartbeat_is_not_fresh(self):
        # Nonpositive epoch is not a heartbeat even if a synthetic observation
        # starts soon after epoch zero (and is therefore within 600 seconds).
        for beat in (0, -1):
            with self.subTest(heartbeat=beat):
                def mutation(d):
                    d["statuses"]["NOX-V46-01"].update(
                        state="RUNNING", heartbeat_unix=beat)
                    d["queues"]["native/001"]["state"] = "running"
                    d["events"]["native/001"]["state"] = "running"
                    d["s03"]["native/001"]["event_sha256"] = digest(
                        d["events"]["native/001"])
                out = self.check(mutation, now_unix=100)
                self.assertEqual(out["crosschecked_queue_s03_pairs"], 0)
                self.assertEqual(out["stale_heartbeat_holds"], ["NOX-V46-01"])
                self.assertFalse(out["native_pass"])

    @staticmethod
    def _add_r60_alias(d, *, replace=False):
        original_tid, original_jid = "NOX-V46-01", "native/001"
        alias_tid, alias_jid = "R60-001", "native/002"
        status = deepcopy(d["statuses"][original_tid])
        status.update(task_id=alias_tid, job_id=alias_jid)
        queue = deepcopy(d["queues"][original_jid])
        queue.update(task_id=alias_tid, job_id=alias_jid)
        event = deepcopy(d["events"][original_jid])
        event.update(task_id=alias_tid, job_id=alias_jid)
        proof = deepcopy(d["s03"][original_jid])
        proof.update(task_id=alias_tid, job_id=alias_jid,
                     event_sha256=digest(event))
        if replace:
            d["statuses"].clear()
            d["queues"].clear()
            d["events"].clear()
            d["s03"].clear()
        d["statuses"][alias_tid] = status
        d["queues"][alias_jid] = queue
        d["events"][alias_jid] = event
        d["s03"][alias_jid] = proof

    def test_mixed_v46_r60_aliases_not_two_logical_tasks(self):
        # Both full, internally consistent source receipts have distinct job IDs.
        # Under the former rule they counted as two despite ONE task number.
        result = self.check(lambda d: self._add_r60_alias(d))
        self.assertEqual(result["state"], "HOLD_MIXED_TASK_FAMILIES")
        self.assertEqual(result["crosschecked_queue_s03_pairs"], 0)
        self.assertFalse(result["native_pass"])

    def test_r60_only_source_family_remains_compatible(self):
        result = self.check(lambda d: self._add_r60_alias(d, replace=True))
        self.assertEqual(result["crosschecked_queue_s03_pairs"], 1)
        self.assertFalse(result["native_pass"])

    def test_empty_is_unknown(self):
        r = self.check(lambda d: (d["statuses"].clear(),d["queues"].clear(),d["s03"].clear(),d["events"].clear()))
        self.assertEqual(r["native_actual_job_count"], "UNKNOWN_NOT_OWNER_SIGNED")


if __name__ == "__main__":
    if sys.argv[1:] != ["--selftest"]:
        raise SystemExit("read-only library; use --selftest (no native IO)")
    unittest.main(argv=[sys.argv[0]], verbosity=2)
