"""Fail-closed API for owner-reviewed systemic manifest publication.

This is a source-side transaction contract only. Runtime adapters must bind each
callback to the existing owner configuration, STOP gate, and native writer
lease. Missing callbacks fail closed; this module never dispatches queue jobs.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath

import owner_systemic_refill as relay

SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST_BYTES = 1024 * 1024
RECEIPT_SCHEMA = "NOX_OWNER_REVIEW_RECEIPT_V1"


class PublishHold(ValueError):
    pass


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise PublishHold("HOLD_REVIEWED_MANIFEST_" + code)


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _input_sha(mission: dict) -> str:
    return _sha(_canonical({
        "mission_id": mission["mission_id"],
        "revision": mission["revision"],
        "root_id": mission["root_id"],
        "context": mission["context"],
        "instruction_sha256": hashlib.sha256(mission["instruction"].encode()).hexdigest(),
        "verification": mission["verification"],
    }))


def _new_missions(previous: dict, candidate: dict) -> list[dict]:
    old = {(m["mission_id"], m["revision"]): m for m in previous["missions"]}
    new = {(m["mission_id"], m["revision"]): m for m in candidate["missions"]}
    _require(all(key in new and new[key] == value for key, value in old.items()),
             "HISTORY_REWRITE")
    added = [mission for key, mission in new.items() if key not in old]
    old_max = {}
    for mission in previous["missions"]:
        old_max[mission["mission_id"]] = max(
            old_max.get(mission["mission_id"], 0), mission["revision"])
    _require(all(m["revision"] > old_max.get(m["mission_id"], 0) for m in added),
             "MISSION_REVISION_REPLAY")
    return added


def publish_reviewed_manifest(expected_previous_sha: str,
                              canonical_manifest_bytes: bytes,
                              owner_review_receipt_sha: str,
                              *, backend):
    """Publish one immutable OWNER_REVIEWED manifest and CAS its live reference.

    Required backend callbacks are intentionally explicit:
      owner_publish_lease(), owner_allowed(), stop_active(), writer_lease(),
      current_manifest_reference(), read_manifest_bytes(sha),
      verify_owner_review_receipt(sha), live_source_registry_pins(),
      admitted_task_ids(), manifest_reference_for_sha(sha),
      write_content_addressed_manifest(path, sha, bytes),
      compare_and_swap_systemic_relay(expected_sha, ref, receipt_sha),
      read_current_manifest_reference().
    Each write callback must return independently read-back state. This routine
    validates that state and never enqueues or accepts a native task.
    """
    _require(isinstance(expected_previous_sha, str)
             and SHA.fullmatch(expected_previous_sha), "PREDECESSOR_SHA")
    _require(isinstance(owner_review_receipt_sha, str)
             and SHA.fullmatch(owner_review_receipt_sha), "REVIEW_RECEIPT_SHA")
    _require(isinstance(canonical_manifest_bytes, bytes)
             and 0 < len(canonical_manifest_bytes) <= MAX_MANIFEST_BYTES,
             "MANIFEST_SIZE")
    candidate = json.loads(canonical_manifest_bytes)
    _require(_canonical(candidate) == canonical_manifest_bytes, "NON_CANONICAL")
    relay.validate_manifest(candidate)
    candidate_sha = _sha(canonical_manifest_bytes)

    required = (
        "owner_publish_lease", "owner_allowed", "stop_active", "writer_lease",
        "current_manifest_reference", "read_manifest_bytes",
        "verify_owner_review_receipt", "live_source_registry_pins",
        "admitted_task_ids", "manifest_reference_for_sha",
        "write_content_addressed_manifest", "compare_and_swap_systemic_relay",
        "read_current_manifest_reference",
    )
    _require(all(callable(getattr(backend, name, None)) for name in required),
             "BACKEND_INCOMPLETE")

    with backend.owner_publish_lease():
        def guard():
            _require(backend.owner_allowed() is True, "OWNER_SCOPE")
            _require(backend.stop_active() is False, "STOP")
            _require(backend.writer_lease() is True, "WRITER_LEASE")

        guard()
        current_ref = backend.current_manifest_reference()
        _require(isinstance(current_ref, dict)
                 and current_ref.get("sha256") == expected_previous_sha,
                 "PREDECESSOR_CAS")
        previous_raw = backend.read_manifest_bytes(expected_previous_sha)
        _require(isinstance(previous_raw, bytes)
                 and _sha(previous_raw) == expected_previous_sha,
                 "PREDECESSOR_READBACK")
        previous = json.loads(previous_raw)
        relay.validate_manifest(previous)
        _require(candidate.get("previous_manifest_sha256") == expected_previous_sha
                 and candidate.get("revision") == previous["revision"] + 1,
                 "ANCESTRY")
        _require(candidate["registry"]["source_registry_sha256"]
                 == backend.live_source_registry_pins(), "SOURCE_REGISTRY_PINS")

        receipt_raw = backend.verify_owner_review_receipt(owner_review_receipt_sha)
        _require(isinstance(receipt_raw, bytes)
                 and _sha(receipt_raw) == owner_review_receipt_sha,
                 "REVIEW_RECEIPT_READBACK")
        receipt = json.loads(receipt_raw)
        _require(_canonical(receipt) == receipt_raw
                 and receipt.get("schema") == RECEIPT_SCHEMA
                 and receipt.get("state") == "OWNER_REVIEWED"
                 and receipt.get("previous_manifest_sha256") == expected_previous_sha
                 and receipt.get("manifest_sha256") == candidate_sha
                 and receipt.get("source_registry_sha256")
                    == candidate["registry"]["source_registry_sha256"]
                 and receipt.get("original_task_accepted") is False,
                 "REVIEW_RECEIPT_SCOPE")

        added = _new_missions(previous, candidate)
        admitted = backend.admitted_task_ids()
        _require(isinstance(admitted, (set, frozenset)), "ADMISSION_SNAPSHOT")
        new_ids = {
            mission["parent_task_id"] + ".relay." + mission["mission_id"] + "."
            + _input_sha(mission)[:16]
            for mission in added
        }
        _require(len(new_ids) == len(added) and not (new_ids & set(admitted)),
                 "DUPLICATE_TASK_ID")

        reference = backend.manifest_reference_for_sha(candidate_sha)
        _require(isinstance(reference, dict)
                 and set(reference) == {"path", "sha256"}
                 and reference["sha256"] == candidate_sha,
                 "CONTENT_ADDRESS_REFERENCE")
        target = PurePosixPath(reference["path"])
        _require(target.is_absolute() and target.name == candidate_sha + ".json"
                 and target.parent.name == "relay", "CONTENT_ADDRESS_PATH")

        guard()
        readback = backend.write_content_addressed_manifest(
            reference["path"], candidate_sha, canonical_manifest_bytes)
        _require(readback == canonical_manifest_bytes, "CONTENT_ADDRESS_READBACK")
        guard()
        cas_result = backend.compare_and_swap_systemic_relay(
            expected_previous_sha, reference, owner_review_receipt_sha)
        _require(isinstance(cas_result, dict)
                 and cas_result.get("sha256") == candidate_sha
                 and cas_result.get("path") == reference["path"],
                 "CAS_RECEIPT")
        guard()
        exact_ref = backend.read_current_manifest_reference()
        _require(exact_ref == reference, "CAS_READBACK")
        return {
            "schema": "NOX_REVIEWED_MANIFEST_PUBLISH_RECEIPT_V1",
            "state": "PUBLISHED_SOURCE_MANIFEST",
            "previous_manifest_sha256": expected_previous_sha,
            "manifest_sha256": candidate_sha,
            "owner_review_receipt_sha256": owner_review_receipt_sha,
            "added_mission_count": len(added),
            "new_task_ids": sorted(new_ids),
            "original_task_accepted": False,
            "native_jobs_published": 0,
        }
