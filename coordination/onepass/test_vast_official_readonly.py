"""No-network, no-auth regression tests for read-only official Vast SDK/CLI doctor."""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from coordination.onepass import vast_official_readonly as doctor


class VastOfficialReadOnlyTests(unittest.TestCase):
    def test_detect_exact_instance_only(self):
        items = [{"id": 13, "actual_status": "running"},
                 {"id": 60509551, "actual_status": "running"}]
        result = doctor.safe_summary("SDK", {"instances": items})
        self.assertEqual(result["state"], "TARGET_VISIBLE")
        self.assertEqual(result["target_state"], "running")
        self.assertEqual(result["target_count"], 1)
        self.assertNotIn("ip", result)
    def test_absence_is_not_deleted_claim(self):
        result = doctor.safe_summary("CLI", [{"id": 101}])
        self.assertEqual(result["state"], "HOLD_TARGET_NOT_VISIBLE")
        self.assertNotIn("destroyed", str(result).lower())
    def test_invalid_schema_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "HOLD_INSTANCE_LIST_SCHEMA"):
            doctor.safe_summary("CLI", {"not_instances": []})
        with self.assertRaisesRegex(ValueError, "HOLD_INSTANCE_ITEMS_SCHEMA"):
            doctor.safe_summary("CLI", [None])
    def test_error_code_redaction(self):
        self.assertEqual(doctor.classify_failure("HTTPError: 404 no access"), "HTTP_404")
        self.assertEqual(doctor.classify_failure("status=401 invalid password"), "HTTP_401")
        self.assertEqual(doctor.classify_failure("hello SECRET_TOKEN"), "CLIENT_ERROR")
    def test_dangerous_cli_operations_blocked(self):
        for word in ["create", "destroy", "stop", "reboot", "--api-key"]:
            with self.assertRaisesRegex(RuntimeError, "HOLD_FORBIDDEN_CLI_OPERATION"):
                doctor.command_readonly("test", ["vastai", word, "instances"])
    def test_missing_key_does_not_attempt_network(self):
        with patch.dict(os.environ, {"NOX2": ""}):
            with patch.object(doctor.subprocess, "run") as fake:
                outcome = doctor.command_readonly("CLI", ["vastai", "show", "instances", "--raw"])
        self.assertEqual(outcome["state"], "HOLD_NOX2")
        fake.assert_not_called()
    def test_failure_sanitized_and_token_not_written(self):
        secret = "do-not-print-this-key"
        with patch.dict(os.environ, {"NOX2": secret}):
            def fake(cmd, **kw):
                self.assertEqual(kw["env"]["VAST_API_KEY"], secret)
                self.assertFalse(any(secret in arg for arg in cmd))
                return SimpleNamespace(returncode=1, stderr="HTTPError 404: private details", stdout="")
            with patch.object(doctor.subprocess, "run", side_effect=fake):
                outcome = doctor.command_readonly("CLI", ["vastai", "show", "instances", "--raw"])
        self.assertEqual(outcome["state"], "HOLD_HTTP_404")
        self.assertNotIn(secret, str(outcome))


if __name__ == "__main__":
    unittest.main()
