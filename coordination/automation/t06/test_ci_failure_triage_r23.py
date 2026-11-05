"""Focused offline tests for the read-only NOX CI triage."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).with_name("ci_failure_triage_r23.py")
spec = importlib.util.spec_from_file_location("ci_failure_triage_r23", path)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


class TestCIFailureTriage(unittest.TestCase):
    def test_missing_steps_not_mislabelled_code_failure(self):
        def fetch(path, token):
            if path.endswith("/jobs?per_page=100"):
                return {"total_count": 1, "jobs": [
                    {"id": 9, "name": "p01-source-regression",
                     "steps": None, "conclusion": "failure"}]}
            return {"head_sha": "a" * 40, "event": "pull_request",
                    "conclusion": "failure"}
        with patch.object(triage, "api_get", side_effect=fetch):
            result = triage.diagnose_run("owner/repo", 1, "test")
        self.assertEqual(result["jobs"][0]["classification"],
                         "NO_STEPS_CAUSE_UNKNOWN")
        self.assertFalse(result["source_ready"])
        self.assertFalse(result["independent_qa_accepted"])

    def test_failed_steps_do_not_imply_source_ready(self):
        def fetch(path, token):
            if path.endswith("/jobs?per_page=100"):
                return {"total_count": 1, "jobs": [{
                    "id": 1, "conclusion": "failure", "steps": [{
                        "name": "test", "number": 2, "conclusion": "failure"}]}]}
            return {"head_sha": "a" * 40}
        with patch.object(triage, "api_get", side_effect=fetch):
            result = triage.diagnose_run("owner/repo", 1, "test")
        self.assertEqual(result["jobs"][0]["classification"],
                         "FAILED_STEPS_PRESENT_INSPECT_LOGS")
        self.assertFalse(result["source_ready"])

    def test_pagination_fails_closed(self):
        with patch.object(triage, "api_get", side_effect=[
            {"head_sha": "a" * 40},
            {"total_count": 101, "jobs": []}]):
            with self.assertRaisesRegex(ValueError, "PAGINATION_REQUIRED"):
                triage.diagnose_run("owner/repo", 1, "test")


if __name__ == "__main__":
    unittest.main()
