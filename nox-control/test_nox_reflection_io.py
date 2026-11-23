#!/usr/bin/env python3
"""Focused 4B04 input-admission regression: never read a switched pathname."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from nox_reflection import MAX_INPUT_BYTES, ReflectionError, _load_input, main


class ReflectionInputAdmission(unittest.TestCase):
    def test_evidence_reference_paths_never_publish_credential_like_segments(self):
        from nox_reflection import _https_reference
        synthetic = "ghp_" + "A" * 24  # Test-only marker, not a credential.
        for path in (
            "/evidence/" + synthetic,
            "/evidence/ghp%5f" + "A" * 24,
            "/evidence/%2567hp%255f" + "A" * 24,
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ReflectionError, "credential-like"):
                    _https_reference("https://example.org" + path, "test.url")
        # Four nested percent-encoding layers bypassed the former
        # three-pass decoder, letting credential-like path evidence through.
        from urllib.parse import quote
        for depth in (4, 8):
            encoded = "ghp%5f" + "A" * 24  # Synthetic marker only.
            for _ in range(depth - 1):
                encoded = quote(encoded, safe="")
            with self.subTest(nesting_depth=depth):
                with self.assertRaisesRegex(ReflectionError, "credential-like"):
                    _https_reference("https://example.org/evidence/" + encoded, "test.url")
        # Even pathological encoding depth must HOLD, not pass still-hidden
        # evidence or spend unbounded CPU decoding it.
        deeply_nested = "ghp%5f" + "A" * 24
        for _ in range(40):
            deeply_nested = quote(deeply_nested, safe="")
        with self.assertRaisesRegex(ReflectionError, "nested URL encoding"):
            _https_reference("https://example.org/evidence/" + deeply_nested, "test.url")
        self.assertEqual(
            _https_reference("https://github.com/org/repo/actions/runs/123?token=fake", "test.url"),
            "https://github.com/org/repo/actions/runs/123",
        )

    def test_reflection_chronology_requires_a_real_causal_order(self):
        from nox_reflection import (
            INPUT_SCHEMA, TASK_SPEC_SHA256, SOURCE_REGISTRY_BLOB_SHA,
            validate_record,
        )
        record = {
            "schema": INPUT_SCHEMA,
            "record_id": "a6-4b04-chronology-synthetic",
            "task": {
                "id": "4B04", "spec_sha256": TASK_SPEC_SHA256,
                "registry_blob_sha": SOURCE_REGISTRY_BLOB_SHA,
            },
            "failure": {
                "observed_at": "2026-11-22T03:00:00+03:00",
                "summary": "Synthetic public failure",
                "evidence_url": "https://example.org/issue",
                "evidence_sha256": "a" * 64,
            },
            "hypothesis": {"statement": "Synthetic causal hypothesis",
                           "observable": "A bounded public test result"},
            "change": {
                "branch": "repair/chronology-proof", "commit_sha": "b" * 40,
                "diff_sha256": "c" * 64, "files": ["nox-control/example.py"],
                "permission_receipt_url": "https://example.org/permission",
                "permission_receipt_sha256": "d" * 64,
            },
            "verification": {
                "status": "FAIL", "verified_at": "2026-11-21T23:59:59Z",
                "target_commit_sha": "b" * 40,
                "receipt_url": "https://example.org/check",
                "artifact_sha256": "e" * 64,
            },
        }
        # The report's wall-clock date can precede the failure's local
        # date yet still represent a later UTC instant; compare instants.
        with self.assertRaisesRegex(ReflectionError, "predate"):
            validate_record(record)
        record["verification"]["verified_at"] = "2026-11-22T00:00:00.000001Z"
        self.assertEqual(validate_record(record)["original_task_accepted"], False)
        # One second before the failure is still invalid, even in FAIL.
        record["verification"]["verified_at"] = "2026-11-22T02:59:59+03:00"
        with self.assertRaisesRegex(ReflectionError, "predate"):
            validate_record(record)

    def test_regular_json_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            path.write_text('{"sample":"ok"}', encoding="utf-8")
            self.assertEqual(_load_input(str(path)), {"sample": "ok"})

    def test_ambiguous_json_is_rejected_before_any_reflection_receipt(self):
        # json.loads normally uses last-wins duplicate keys and accepts
        # NaN/Infinity. Neither is valid evidence for a source-cycle claim.
        invalid = (
            '{"record_id":"first","record_id":"second"}',
            '{"task":{"id":"4B04","id":"other"}}',
            '{"failure":{"observed_at":"a","observed_at":"b"}}',
            '{"sample":NaN}', '{"sample":Infinity}',
            '{"sample":-Infinity}',
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            for raw in invalid:
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(ReflectionError):
                        _load_input(str(path))
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        result = main(["--input", str(path)])
                    self.assertEqual(result, 2)
                    self.assertEqual(json.loads(err.getvalue())["status"], "HOLD")
            path.write_text('{"sample":{"letters":["ñ","Б"]}}', encoding="utf-8")
            self.assertEqual(_load_input(str(path)),
                             {"sample": {"letters": ["ñ", "Б"]}})

    def test_symlink_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "original.json"
            original.write_text('{"sample":"ok"}', encoding="utf-8")
            shortcut = Path(d) / "input.json"
            shortcut.symlink_to(original)
            with self.assertRaises(ReflectionError):
                _load_input(str(shortcut))

    def test_fifo_and_oversized_input_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            fifo = Path(d) / "fifo.json"
            os.mkfifo(fifo)
            with self.assertRaises(ReflectionError):
                _load_input(str(fifo))
            large = Path(d) / "large.json"
            large.write_bytes(b" " * (MAX_INPUT_BYTES + 1))
            with self.assertRaises(ReflectionError):
                _load_input(str(large))

    def test_invalid_utf8_emits_bounded_hold_without_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invalid.json"
            path.write_bytes(b'{"message":"\\xff"}'.replace(b"\\xff", b"\xff"))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main(["--input", str(path)])
            self.assertEqual(code, 2)
            lines = err.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["status"], "HOLD")
            self.assertNotIn("Traceback", lines[0])


if __name__ == "__main__":
    unittest.main()
