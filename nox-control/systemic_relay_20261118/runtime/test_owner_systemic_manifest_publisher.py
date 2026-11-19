import contextlib
import hashlib
import unittest

import owner_systemic_refill as relay
from owner_systemic_manifest_publisher import (
    PublishHold, _canonical, _input_sha, publish_reviewed_manifest,
)

A, B, C, D, E = ("a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64)
PINS = {"tasks": A, "ideas": B, "receipts": C, "routing": D}


def manifest(revision, previous, missions):
    return {
        "schema": relay.SCHEMA, "revision": revision,
        "previous_manifest_sha256": previous, "review_origin": "OWNER_REVIEWED",
        "acceptance_scope": "SOURCE_PATCH_TESTED", "original_task_accepted": False,
        "registry": {"total_original_ids": 295, "source_registry_sha256": PINS,
                     "parents": {"1A03": {"spec_sha256": E,
                         "queue_id": "Q1_RUNTIME_CHAT", "required_evidence": "source"}}},
        "missions": missions, "research_topics": [],
    }


MISSION = {
    "mission_id": "chat_context", "revision": 1, "parent_task_id": "1A03",
    "queue_id": "Q1_RUNTIME_CHAT", "priority": "P0",
    "repeat_policy": "ONCE_PER_REVIEWED_REVISION", "root_id": "root1",
    "title": "Preserve chat context", "instruction": "Preserve context from pinned source.",
    "context": [{"path": "src/app.py", "sha256": A},
                {"path": "tests/test_chat.py", "sha256": B}],
    "editable_paths": ["src/app.py"], "allowed_new_paths": [],
    "verification": {"kind": "python_unittest", "modules": ["tests.test_chat"],
                     "min_tests": 1, "timeout_sec": 30},
    "dependencies": [], "focus_regions": [], "experience": [],
    "budget": {"lane": "model", "max_model_turns": 24, "cpu_seconds": 30,
               "max_searches": 0, "max_output_bytes": 4096},
    "defect": {"observed_source_sha256": A, "finding": "Observed bounded defect.",
               "expected_delta": "Preserve the conversation identifier.",
               "verification_limit": "Source checks do not prove live acceptance."},
}


class Backend:
    def __init__(self):
        self.previous_raw = _canonical(manifest(1, None, []))
        self.previous_sha = hashlib.sha256(self.previous_raw).hexdigest()
        self.candidate_raw = _canonical(manifest(2, self.previous_sha, [MISSION]))
        self.candidate_sha = hashlib.sha256(self.candidate_raw).hexdigest()
        self.receipt_raw = _canonical({
            "schema": "NOX_OWNER_REVIEW_RECEIPT_V1", "state": "OWNER_REVIEWED",
            "previous_manifest_sha256": self.previous_sha,
            "manifest_sha256": self.candidate_sha, "source_registry_sha256": PINS,
            "original_task_accepted": False,
        })
        self.receipt_sha = hashlib.sha256(self.receipt_raw).hexdigest()
        self.ref = self.ref_for(self.previous_sha)
        self.admitted, self.writes, self.cas_calls = set(), 0, 0
        self.stopped, self.readback_override = False, None

    @staticmethod
    def ref_for(sha):
        return {"path": "/package/relay/" + sha + ".json", "sha256": sha}

    @contextlib.contextmanager
    def owner_publish_lease(self): yield
    def owner_allowed(self): return True
    def stop_active(self): return self.stopped
    def writer_lease(self): return True
    def current_manifest_reference(self): return self.ref
    def read_manifest_bytes(self, sha):
        return self.previous_raw if sha == self.previous_sha else None
    def verify_owner_review_receipt(self, sha):
        return self.receipt_raw if sha == self.receipt_sha else None
    def live_source_registry_pins(self): return PINS
    def admitted_task_ids(self): return set(self.admitted)
    def manifest_reference_for_sha(self, sha): return self.ref_for(sha)

    def write_content_addressed_manifest(self, path, sha, raw):
        self.writes += 1
        self.stored = (path, sha, raw)
        return raw if self.readback_override is None else self.readback_override

    def compare_and_swap_systemic_relay(self, expected, reference, receipt_sha):
        self.cas_calls += 1
        if self.ref["sha256"] != expected:
            raise RuntimeError("CAS mismatch")
        self.ref = reference
        return dict(reference)

    def read_current_manifest_reference(self): return dict(self.ref)


class PublisherTests(unittest.TestCase):
    def publish(self, backend):
        return publish_reviewed_manifest(
            backend.previous_sha, backend.candidate_raw, backend.receipt_sha,
            backend=backend)

    def test_publishes_source_manifest_without_native_jobs(self):
        b = Backend()
        result = self.publish(b)
        self.assertEqual(result["state"], "PUBLISHED_SOURCE_MANIFEST")
        self.assertEqual(result["native_jobs_published"], 0)
        self.assertEqual((b.writes, b.cas_calls), (1, 1))
        self.assertEqual(b.stored[1], result["manifest_sha256"])

    def test_stop_holds_before_write(self):
        b = Backend()
        b.stopped = True
        with self.assertRaisesRegex(PublishHold, "HOLD_REVIEWED_MANIFEST_STOP"):
            self.publish(b)
        self.assertEqual((b.writes, b.cas_calls), (0, 0))

    def test_duplicate_task_id_holds_before_write(self):
        b = Backend()
        b.admitted.add("1A03.relay.chat_context." + _input_sha(MISSION)[:16])
        with self.assertRaisesRegex(PublishHold, "DUPLICATE_TASK_ID"):
            self.publish(b)
        self.assertEqual((b.writes, b.cas_calls), (0, 0))

    def test_mismatched_owner_receipt_holds(self):
        b = Backend()
        receipt = {"schema": "NOX_OWNER_REVIEW_RECEIPT_V1", "state": "OWNER_REVIEWED",
            "previous_manifest_sha256": b.previous_sha, "manifest_sha256": E,
            "source_registry_sha256": PINS, "original_task_accepted": False}
        b.receipt_raw = _canonical(receipt)
        b.receipt_sha = hashlib.sha256(b.receipt_raw).hexdigest()
        with self.assertRaisesRegex(PublishHold, "REVIEW_RECEIPT_SCOPE"):
            self.publish(b)
        self.assertEqual(b.writes, 0)

    def test_storage_readback_mismatch_never_cas_updates(self):
        b = Backend()
        b.readback_override = b"different"
        with self.assertRaisesRegex(PublishHold, "CONTENT_ADDRESS_READBACK"):
            self.publish(b)
        self.assertEqual(b.cas_calls, 0)
        self.assertEqual(b.ref["sha256"], b.previous_sha)


if __name__ == "__main__":
    unittest.main()
