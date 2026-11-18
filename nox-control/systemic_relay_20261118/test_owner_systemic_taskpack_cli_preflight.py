"""Focused regression: reject invalid taskpack publisher preflight before disk writes.

Run: python nox-control/systemic_relay_20261118/test_owner_systemic_taskpack_cli_preflight.py
Source-only; never reaches native owner/server.
"""
import contextlib
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
    def _run(self, checkpoint=None, template=None, helper=None, source_pin="same"):
        args = SimpleNamespace(
            previous_manifest="previous", previous_sha256="previous-sha",
            proposal="proposal", source_census="census", registry="registry",
            review="review", output="/not-used",
            publisher_checkpoint=checkpoint, publisher_template=template,
            transaction_helper=helper,
        )
        inputs = {
            "previous": ({}, "previous-sha"),
            "proposal": ({}, "proposal-sha"),
            "census": ({"observed_files_sha256": "same"}, "census-sha"),
            "registry": ({}, "registry-sha"),
            "review": ({}, "review-sha"),
            "checkpoint": ({"expected_source_files_sha256": source_pin}, "checkpoint-sha"),
        }
        events = []
        def write(*a, **kw):
            events.append("write_package")
            return {"state": "SOURCE_PREPARED"}
        def publisher(*a, **kw):
            events.append("publisher_entry")
            return {"native_execution_performed": False}
        with patch.object(taskpack.argparse.ArgumentParser, "parse_args", return_value=args), \
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
                                    helper="helper", source_pin="stale")
        self.assertIn("PUBLISH_CENSUS_PIN", outcome)
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
