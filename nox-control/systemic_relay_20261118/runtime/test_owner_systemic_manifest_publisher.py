import contextlib
import hashlib
import json
import unittest

import owner_systemic_refill as relay
from owner_systemic_manifest_publisher import (
    PublishHold, _canonical, _input_sha, publish_reviewed_manifest,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def manifest(revision, previous, missions):
    return {
        "schema": relay.SCHEMA,
        "revision": revision,
        "previous_manifest_sha256": previous,
        "review_origin": "OWNER_REVIEWED",
        "acceptance_scope": "SOURCE_PATCH_TESTED",
        "original_task_accepted": False,
        "registry": {
            "total_original_ids": 295,
            "source_registry_sha256": {
                "tasks": SHA_A, "ideas": SHA_B, "receipts": SHA_C,
                "routing": "d" * 64,
            },
            "parents": {
                "1A03": {"spec_sha256": "e" * 64,
                         "queue_id": "Q1_RUNTIME_CHAT",
                         "required_evidence": "source"},
            },
        },
        "missions": missions,
        "research_topics": [],
    }


def mission():
    return {
        "mission_id": "chat_context",
        "revision": 1,
        "parent_task_id": "1A03",
        "queue_id": "Q1_RUNTIME_CHAT",
        "priority": "P0",
        "repeat_policy": "ONCE_PER_REVIEWED_REVISION",
        "root_id": "root1",
        "title": "Preserve chat context",
        "instruction": "Use the pinned source evidence to preserve context.",
        "context": [
            {"path": "src/app.py", "sha256": SHA_A},
            {"path": "tests/test_chat.py", "sha256": SHA_B},
        ],
        "editable_paths": ["src/app.py"],
        "allowed_new_paths": [],
        "verification": {
            "kind": "python_unittest",
            "modules": ["tests.test_chat"],
            "min_tests": 1,
            "timeout_sec": 30,
        },
        "dependencies": [],
        "focus_regions": [],
        "experience": [],
        "budget": {
            "lane": "model", "max_model_turns": 24, "cpu_seconds": 30,
            "max_searches": 0, "max_output_bytes": 4096,
        },
        "defect": {
            "observed_source_sha256": SHA_A,
            "finding": "Observed bounded defect.",
            "expected_delta": "Preserve the conversation identifier.",
            "verification_limit": "Source tests do not establish live acceptance.",
        },
    }


class Backend:
    def __init__(self):
        self.previous = manifest(1, None, [])
        self.previous_raw = _canonical(self.previous)
        self.previous_sha = hashlib.sha256(self.previous_raw).hexdigest()
        self.candidate = manifest(2, self.previous_sha, [mission()])
        self.candidate_raw = _canonical(self.candidate)
        self.candidate_sha = hashlib.sha256(self.candidate_raw).hexdigest()
        receipt = {
            "schema": "NOX_OWNER_REVIEW_RECEIPT_V1",
            "state": "OWNER_REVIEWED",
            "previous_manifest_sha256": self.previous_sha,
            "manifest_sha256": self.candidate_sha,
            "source_registry_sha256":
                self.candidate["registry"]["source_registry_sha256"],
            "original_task_accepted": False,
        }
        self.receipt_raw = _canonical(receipt)
        self.receipt_sha = hashlib.sha256(self.receipt_raw).hexdigest()
        self.ref = self.ref_for(self.previous_sha)
        self.admitted = set()
        self.writes = 0
        self.cas_calls = 0
        self.stopped = False
        self.readback_override = None

    @staticmethod
    def ref_for(sha):
        return {"path": "/package/relay/" + sha + ".json", "sha256": sha}

    @contextlib.contextmanager
    def owner_publish_lease(self):
        yield

    def owner_allowed(self): return True
    def stop_active(self): return self.stopped is True
    def writer_lease(self): return True
    def current_manifest_reference(self): return self.ref
    def read_manifest_bytes(self, sha):
        return self.previous_raw if sha == self.previous_sha else None
    def verify_owner_review_receipt(self, sha):
        return self.receipt_raw if sha == self.receipt_sha else None
    def live_source_registry_pins(self):
        return self.candidate["registry"]["source_registry_sha256"]
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

    def read_current_manifest_reference(self):
        return dict(self.ref)


class ReviewedManifestPublisherTests(unittest.TestCase):
    def call(self, backend):
        return publish_reviewed_manifest(
            backend.previous_sha, backend.candidate_raw, backend.receipt_sha,
            backend=backend,
        )

    def test_publishes_content_then_exact_cas_without_native_jobs(self):
        backend = Backend()
        receipt = self.call(backend)
        self.assertEqual(receipt["state"], "PUBLISHED_SOURCE_MANIFEST")
        self.assertEqual(receipt["native_jobs_published"], 0)
        self.assertEqual(backend.writes, 1)
        self.assertEqual(backend.cas_calls, 1)
        self.assertEqual(backend.stored[1], receipt["manifest_sha256"])

    def test_stop_fails_before_any_write(self):
        backend = Backend()
        backend.stopped = True
        with self.assertRaisesRegex(PublishHold, "HOLD_REVIEWED_MANIFEST_STOP"):
            self.call(backend)
        self.assertEqual(backend.writes, 0)
        self.assertEqual(backend.cas_calls, 0)

    def test_duplicate_admitted_task_fails_before_any_write(self):
        backend = Backend()
        task_id = "1A03.relay.chat_context." + _input_sha(mission())[:16]
        backend.admitted.add(task_id)
        with self.assertRaisesRegex(PublishHold, "DUPLICATE_TASK_ID"):
            self.call(backend)
        self.assertEqual(backend.writes, 0)
        self.assertEqual(backend.cas_calls, 0)

    def test_wrong_receipt_manifest_pin_fails_before_any_write(self):
        backend = Backend()
        backend.receipt_raw = _canonical({
            "schema": "NOX_OWNER_REVIEW_RECEIPT_V1",
            "state": "OWNER_REVIEWED",
            "previous_manifest_sha256": backend.previous_sha,
            "manifest_sha256": "f" * 64,
            "source_registry_sha256":
                backend.candidate["registry"]["source_registry_sha256"],
            "original_task_accepted": False,
        })
        backend.receipt_sha = hashlib.sha256(backend.receipt_raw).hexdigest()
        with self.assertRaisesRegex(PublishHold, "REVIEW_RECEIPT_SCOPE"):
            self.call(backend)
        self.assertEqual(backend.writes, 0)

    def test_content_readback_mismatch_never_updates_reference(self):
        backend = Backend()
        backend.readback_override = b"different"
        with self.assertRaisesRegex(PublishHold, "CONTENT_ADDRESS_READBACK"):
            self.call(backend)
        self.assertEqual(backend.cas_calls, 0)
        self.assertEqual(backend.ref["sha256"], backend.previous_sha)


if __name__ == "__main__":
    unittest.main()
