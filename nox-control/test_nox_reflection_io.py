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
    def test_regular_json_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            path.write_text('{"sample":"ok"}', encoding="utf-8")
            self.assertEqual(_load_input(str(path)), {"sample": "ok"})

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
