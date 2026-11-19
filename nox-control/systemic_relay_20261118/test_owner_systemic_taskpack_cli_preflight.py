"""Focused regression: reject invalid taskpack publisher preflight before disk writes.

Run: python nox-control/systemic_relay_20261118/test_owner_systemic_taskpack_cli_preflight.py
Source-only; never reaches native owner/server.
"""
import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owner_systemic_taskpack as taskpack


class TaskpackPublisherPreflightTest(unittest.TestCase):
    def _run(self, checkpoint=None, template=None, helper=None, source_pin=None, malformed=False):
        args = SimpleNamespace(
            previous_manifest="previous", previous_sha256="c" * 64,
            proposal="proposal", source_census="census", registry="registry",
            review="review", output="/not-used",
            publisher_checkpoint=("checkpoint" if checkpoint else None), publisher_template=("template" if template else None),
            transaction_helper=("helper" if helper else None),
        )
        source_pin = source_pin or "b" * 64
        template_bytes = b"\nSPEC = {}\nclass Publisher:\n    BUNDLE = __NOX_BUNDLE_JSON__\n"
        helper_bytes = b"synthetic transaction helper"
        checkpoint_record = {
            "schema": "NOX_SYSTEMIC_NATIVE_PUBLISH_CHECKPOINT_V1",
            "expected_config_sha256": "a" * 64,
            "previous_manifest_sha256": "c" * 64,
            "expected_source_files_sha256": source_pin,
            "publisher_template_sha256": hashlib.sha256(template_bytes).hexdigest(),
            "expected_director": {"pid": 10, "start_ticks": 100},
            "expected_workers": [
                {"pid": 11, "start_ticks": 101},
                {"pid": 12, "start_ticks": 102},
                {"pid": 13, "start_ticks": 103},
            ],
            "protected_processes": {
                "chat": {"pid": 20, "start_ticks": 200},
                "proxy": {"pid": 21, "start_ticks": 201},
                "web": {"pid": 22, "start_ticks": 202},
            },
        }
        if malformed:
            checkpoint_record.pop("expected_workers")
        inputs = {
            "previous": ({}, "c" * 64),
            "proposal": ({}, "proposal-sha"),
            "census": ({"observed_files_sha256": "b" * 64}, "census-sha"),
            "registry": ({}, "registry-sha"),
            "review": ({}, "review-sha"),
            "checkpoint": (checkpoint_record, "checkpoint-sha"),
        }
        events = []
        def write(*a, **kw):
            events.append("write_package")
            return {"state": "SOURCE_PREPARED"}
        def publisher(*a, **kw):
            events.append("publisher_entry")
            return {"native_execution_performed": False}
        raw_by_path = {"template": template_bytes, "helper": helper_bytes}
        with patch.object(taskpack, "HELPER_SHA", hashlib.sha256(helper_bytes).hexdigest()), \
             patch.object(taskpack, "read_raw", side_effect=lambda path: raw_by_path[path]), \
             patch.object(taskpack.argparse.ArgumentParser, "parse_args", return_value=args), \
             patch.object(taskpack, "read_document", side_effect=lambda path: inputs[path]), \
             patch.object(taskpack, "compile_taskpack", return_value={"revision": 2}), \
             patch.object(taskpack, "write_package", side_effect=write), \
             patch.object(taskpack, "publisher_entry", side_effect=publisher), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                result = taskpack.main()
            except taskpack.RefillHold as err:
                result = str(err)
        return result, events

    def test_partial_publisher_args_do_not_create_package(self):
        outcome, events = self._run(checkpoint="checkpoint")
        self.assertIn("PUBLISHER_ARGUMENTS", outcome)
        self.assertEqual([], events)

    def test_stale_publisher_source_pin_does_not_create_package(self):
        outcome, events = self._run(checkpoint="checkpoint", template="template",
                                    helper="helper", source_pin="d" * 64)
        self.assertIn("PUBLISH_CENSUS_PIN", outcome)
        self.assertEqual([], events)

    def test_malformed_worker_checkpoint_does_not_create_package(self):
        outcome, events = self._run(checkpoint="checkpoint", template="template",
                                    helper="helper", malformed=True)
        self.assertIn("CHECKPOINT_WORKERS", outcome)
        self.assertEqual([], events)

    def test_non_publisher_package_still_created_once(self):
        outcome, events = self._run()
        self.assertEqual(0, outcome)
        self.assertEqual(["write_package"], events)

    def test_valid_publisher_build_runs_after_package_creation(self):
        outcome, events = self._run(checkpoint="checkpoint", template="template",
                                    helper="helper")
        self.assertEqual(0, outcome)
        self.assertEqual(["write_package", "publisher_entry"], events)


if __name__ == "__main__":
    unittest.main()
