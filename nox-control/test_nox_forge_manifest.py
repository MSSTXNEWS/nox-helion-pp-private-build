#!/usr/bin/env python3
"""Focused 4B01 regression: malformed provenance URLs yield a typed HOLD."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import nox_forge_manifest as forge


class ForgeUrlAuthorityTests(unittest.TestCase):
    def test_invalid_authorities_fail_closed_without_tracebacks(self):
        for url in ("https://[invalid", "https://example.org:not-a-port/source",
                    "https://[::1", "https://example.org:99999/file"):
            with self.subTest(url=url):
                with self.assertRaises(forge.ForgeError):
                    forge._reference(url, "source.source_url")

    def test_normal_https_reference_still_normalizes(self):
        self.assertEqual(
            forge._reference("https://example.org:443/research?a=1", "source.source_url"),
            "https://example.org/research",
        )

    def test_cli_emits_machine_readable_hold(self):
        sha = "0" * 64
        payload = {
            "schema": forge.INPUT_SCHEMA,
            "manifest_id": "authority-hold",
            "created_at": "2026-11-20T07:00:00Z",
            "task": {"id": forge.TASK_ID, "spec_sha256": forge.TASK_SPEC_SHA256,
                     "registry_blob_sha": forge.SOURCE_REGISTRY_BLOB_SHA},
            "sources": [{
                "source_id": "s1", "origin_kind": "VERIFIED_KNOWLEDGE",
                "source_url": "https://[invalid",
                "source_sha256": sha, "license_id": "MIT",
                "license_url": "https://example.org/license",
                "license_sha256": sha, "permission_status": "ALLOWED",
                "permission_receipt": {"url": "https://example.org/evidence",
                                       "sha256": sha,
                                       "observed_at": "2026-11-20T07:00:00Z"},
            }],
            "examples": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = forge.main(["--input", str(path)])
        self.assertEqual(status, 2)
        receipt = json.loads(stderr.getvalue())
        self.assertEqual(receipt["status"], "HOLD")
        self.assertIn("ForgeError", receipt["error"])



class ForgeContentDedupeTests(unittest.TestCase):
    def test_cross_source_duplicate_digest_fails_closed(self):
        sha = "0" * 64
        timestamp = "2026-11-20T11:00:00Z"

        def source(sid):
            return {
                "source_id": sid,
                "origin_kind": "VERIFIED_KNOWLEDGE",
                "source_url": f"https://example.org/{sid}",
                "source_sha256": sha,
                "license_id": "MIT",
                "license_url": "https://example.org/license",
                "license_sha256": sha,
                "permission_status": "ALLOWED",
                "permission_receipt": {
                    "url": "https://example.org/evidence",
                    "sha256": sha,
                    "observed_at": timestamp,
                },
            }

        def example(eid, sid, digest):
            return {
                "example_id": eid,
                "source_id": sid,
                "source_record_id": f"record-{eid}",
                "content_sha256": digest,
                "captured_at": timestamp,
            }

        payload = {
            "schema": forge.INPUT_SCHEMA,
            "manifest_id": "dedupe-content",
            "created_at": timestamp,
            "task": {
                "id": forge.TASK_ID,
                "spec_sha256": forge.TASK_SPEC_SHA256,
                "registry_blob_sha": forge.SOURCE_REGISTRY_BLOB_SHA,
            },
            "sources": [source("s1"), source("s2")],
            "examples": [example("e1", "s1", "1" * 64),
                         example("e2", "s2", "1" * 64)],
        }
        with self.assertRaisesRegex(forge.ForgeError, "duplicate candidate content"):
            forge.build_manifest(payload)

        # Distinct claimed content hashes remain allowed; each source
        # contributes one candidate, without claiming bytes were checked.
        payload["examples"][1]["content_sha256"] = "2" * 64
        result = forge.build_manifest(payload)
        self.assertEqual(len(result["candidate_examples"]), 2)
        self.assertEqual([row["share_numerator"] for row in result["source_shares"]], [1, 1])
        self.assertFalse(result["integrity_scope"]["content_hashes_verified"])



if __name__ == "__main__":
    unittest.main()
