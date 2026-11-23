#!/usr/bin/env python3
"""3A04 one focused source-only acceptance: self-model evidence input is bounded."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import nox_self_model as model


class SelfModelInputAdmission(unittest.TestCase):
    def test_regular_utf8_json_is_read_once(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "input.json"
            value = {"snapshot": {"language": ["Б", "ñ"]}}
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(model._load_input(str(path)), value)

    def test_duplicate_nested_fields_and_nonfinite_are_hold(self):
        examples = ('{"task":{"id":"3A04","id":"forged"}}',
                    '{"evidence":{"sha256":"first","sha256":"second"}}',
                    '{"weight":NaN}', '{"weight":Infinity}', '{"weight":-Infinity}')
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "input.json"
            for content in examples:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(model.SelfModelError):
                        model._load_input(str(path))

    def test_symlink_fifo_and_oversized_file_are_hold(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source = base / "real.json"
            source.write_text("{}", encoding="utf-8")
            symlink = base / "link.json"
            symlink.symlink_to(source)
            fifo = base / "input.fifo"
            os.mkfifo(fifo)
            huge = base / "huge.json"
            huge.write_bytes(b" " * (model.MAX_INPUT_BYTES + 1))
            for path in (symlink, fifo, huge):
                with self.subTest(path=path.name), self.assertRaises(model.SelfModelError):
                    model._load_input(str(path))

    def test_path_race_to_symlink_cannot_change_opened_input(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            ordinary = base / "ordinary.json"
            ordinary.write_text("{}", encoding="utf-8")
            private = base / "private.json"
            private.write_text('{"fake_private":"NEVER_EMIT"}', encoding="utf-8")
            actual_open = os.open
            def swap_at_open(path, flags, *args, **kwargs):
                if path == str(ordinary):
                    ordinary.unlink()
                    ordinary.symlink_to(private)
                return actual_open(path, flags, *args, **kwargs)
            with mock.patch.object(model.os, "open", side_effect=swap_at_open):
                with self.assertRaises(model.SelfModelError):
                    model._load_input(str(ordinary))

    def test_growth_after_fstat_is_bounded_by_actual_read(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "growth.json"
            path.write_bytes(b"{}")
            original_read = os.read
            extended = [False]
            def grow_once(fd, count):
                if not extended[0]:
                    extended[0] = True
                    with path.open("ab") as file:
                        file.write(b" " * (model.MAX_INPUT_BYTES + 1))
                return original_read(fd, count)
            with mock.patch.object(model.os, "read", side_effect=grow_once):
                with self.assertRaisesRegex(model.SelfModelError, "grew beyond"):
                    model._load_input(str(path))
            self.assertTrue(extended[0])

    def test_reference_host_aliases_and_malformed_authority_hold(self):
        # These are metadata only: none must be accepted as external proof.
        unsafe = (
            "https://localhost./evidence",
            "https://127.0.0.1./evidence",
            "https://2130706433/evidence",
            "https://0x7f000001/evidence",
            "https://ⓛⓞⓒⓐⓛⓗⓞⓢⓣ/evidence",
            "https://[not-ip]/evidence",
            "https://a／b.example.com/evidence",
            "https://@example.com/evidence",
        )
        for value in unsafe:
            with self.subTest(value=value), self.assertRaises(model.SelfModelError):
                model._reference_url(value, "proof")

    def test_reference_host_canonicalization_preserves_valid_provenance(self):
        self.assertEqual(
            model._reference_url("https://EXAMPLE.COM./release/notes?utm_source=x", "proof"),
            "https://example.com/release/notes",
        )
        self.assertEqual(
            model._reference_url("https://[2001:4860:4860::8888]/release", "proof"),
            "https://[2001:4860:4860::8888]/release",
        )
        self.assertEqual(
            model._reference_url("https://bücher.example/notice", "proof"),
            "https://xn--bcher-kva.example/notice",
        )

    def test_rejected_input_emits_one_bounded_hold(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ambiguous.json"
            path.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                status = model.main(["--input", str(path)])
            self.assertEqual(status, 2)
            data = json.loads(error.getvalue().strip())
            self.assertEqual(data["status"], "HOLD")
            self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
