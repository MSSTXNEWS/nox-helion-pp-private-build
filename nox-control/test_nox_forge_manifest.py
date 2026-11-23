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




class ForgeSourceIdentityTests(unittest.TestCase):
    def test_source_aliases_cannot_inflate_reported_diversity(self):
        digest = "0" * 64
        instant = "2026-11-20T11:00:00Z"

        def source(sid, url, claimed_hash):
            return {
                "source_id": sid, "origin_kind": "VERIFIED_KNOWLEDGE",
                "source_url": url, "source_sha256": claimed_hash,
                "license_id": "MIT", "license_url": "https://example.org/license",
                "license_sha256": digest, "permission_status": "ALLOWED",
                "permission_receipt": {
                    "url": "https://example.org/permission",
                    "sha256": digest, "observed_at": instant,
                },
            }

        payload = {
            "schema": forge.INPUT_SCHEMA, "manifest_id": "alias-sources",
            "created_at": instant,
            "task": {
                "id": forge.TASK_ID, "spec_sha256": forge.TASK_SPEC_SHA256,
                "registry_blob_sha": forge.SOURCE_REGISTRY_BLOB_SHA,
            },
            "sources": [
                source("s1", "https://example.org/one", "1" * 64),
                source("s2", "https://example.org/two", "2" * 64),
            ],
            "examples": [],
        }
        self.assertEqual(len(forge.build_manifest(payload)["sources"]), 2)

        # Identical URLs under distinct IDs are not independent sources.
        payload["sources"][1]["source_url"] = "https://example.org/one"
        with self.assertRaisesRegex(forge.ForgeError, "duplicate source reference"):
            forge.build_manifest(payload)
        payload["sources"][1]["source_url"] = "https://example.org/two"

        # Different URLs carrying identical claimed source bytes cannot be
        # counted as independent proportions without owner reconciliation.
        payload["sources"][1]["source_sha256"] = "1" * 64
        with self.assertRaisesRegex(forge.ForgeError, "duplicate claimed source SHA"):
            forge.build_manifest(payload)


class ForgeJsonIntegrityTests(unittest.TestCase):
    def test_cli_rejects_nested_duplicate_permission_fields_and_nan(self):
        # Duplicate permission or provenance keys must not be shadowed by
        # the last value accepted by ordinary json.loads().
        invalid = (
            '{"sources":[{"permission_status":"DENIED","permission_status":"ALLOWED"}]}',
            '{"permission_receipt":{"sha256":"x","sha256":"y"}}',
            '{"schema":NaN}',
            '{"schema":Infinity}',
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "input.json"
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        rc = forge.main(["--input", str(path)])
                    self.assertEqual(rc, 2)
                    receipt = json.loads(stderr.getvalue())
                    self.assertEqual(receipt["status"], "HOLD")
                    self.assertIn("ForgeError", receipt["error"])


class ForgeInodeReadTests(unittest.TestCase):
    def test_source_input_is_read_from_safe_regular_inode(self):
        # A symlink (including a symlink swapped in at open-time) cannot
        # substitute different metadata after an earlier path check.
        import os
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            real = Path(root) / "safe.json"
            real.write_bytes(b'{"schema":"invalid"}')
            link = Path(root) / "input.json"
            link.symlink_to(real)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(forge.main(["--input", str(link)]), 2)
            self.assertEqual(json.loads(stderr.getvalue())["status"], "HOLD")

            # Opening a regular file is unchanged. A file swapped for a
            # symlink just before the OS open must fail closed, not follow it.
            self.assertEqual(forge._read_manifest_bytes(real), real.read_bytes())
            link.unlink()
            link.write_bytes(b'{"schema":"invalid"}')
            real_open = os.open
            def swap_before_open(file, flags, *args, **kwargs):
                if str(file) == str(link):
                    link.unlink()
                    link.symlink_to(real)
                return real_open(file, flags, *args, **kwargs)
            with mock.patch.object(forge.os, "open", side_effect=swap_before_open):
                with self.assertRaises(OSError):
                    forge._read_manifest_bytes(link)


class ForgeChronologyTests(unittest.TestCase):
    def test_future_claimed_permission_and_capture_are_held(self):
        now = "2026-11-20T11:00:00Z"
        later = "2026-11-20T11:00:00.000001Z"
        digest = "0" * 64
        payload = {
            "schema": forge.INPUT_SCHEMA,
            "manifest_id": "chronology-example",
            "created_at": now,
            "task": {"id": forge.TASK_ID, "spec_sha256": forge.TASK_SPEC_SHA256,
                     "registry_blob_sha": forge.SOURCE_REGISTRY_BLOB_SHA},
            "sources": [{
                "source_id": "s1", "origin_kind": "SUCCESSFUL_ACTION",
                "source_url": "https://example.org/action",
                "source_sha256": digest, "license_id": "MIT",
                "license_url": "https://example.org/license",
                "license_sha256": digest, "permission_status": "ALLOWED",
                "permission_receipt": {"url": "https://example.org/permission",
                                       "sha256": digest, "observed_at": now},
            }],
            "examples": [{
                "example_id": "e1", "source_id": "s1", "source_record_id": "r1",
                "content_sha256": "1" * 64, "captured_at": now,
            }],
        }
        accepted = forge.build_manifest(payload)
        self.assertEqual(accepted["source_shares"][0]["example_count"], 1)
        self.assertFalse(accepted["integrity_scope"]["permission_receipts_verified"])

        payload["sources"][0]["permission_receipt"]["observed_at"] = later
        with self.assertRaisesRegex(forge.ForgeError, "permission observation"):
            forge.build_manifest(payload)
        payload["sources"][0]["permission_receipt"]["observed_at"] = now

        payload["examples"][0]["captured_at"] = later
        with self.assertRaisesRegex(forge.ForgeError, "candidate capture"):
            forge.build_manifest(payload)


if __name__ == "__main__":
    unittest.main()
