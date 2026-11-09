"""B04: original P03 owner3 ACK cannot promote component-prefixed denials."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/P03/Source/python-host/p03_onehost_port.py"
spec = importlib.util.spec_from_file_location("nox_p03_existing_owner3", SOURCE)
owner3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner3)


class OriginalOwner3StatusAck(unittest.TestCase):
    def test_component_prefixed_owner_denials_hold(self):
        for status in (
            "PROVIDER_OFFLINE_HOLD", "OWNER_PERMISSION_REQUIRED",
            "SID_MISMATCH", "ACL_MISMATCH", "NOT_READY",
            "MODEL_NOT_INSTALLED", "CONSENT_REQUIRED", "AUTH_REQUIRED",
            "OWNER_REVOKED", "OWNER_UNAVAILABLE", "TIMED_OUT",
            "REVIEW_REQUIRED",
        ):
            with self.subTest(status=status):
                self.assertTrue(owner3._owner3_status_denied(status))

    def test_valid_existing_queue_states_unchanged(self):
        for status in ("QUEUED", "COMPLETED", "CANCELLED",
                       "SELECTED_PENDING_NATIVE_E07"):
            with self.subTest(status=status):
                self.assertFalse(owner3._owner3_status_denied(status))

    def test_no_ambiguous_or_unbounded_ack_status(self):
        for status in ("", " ", "###", "QUEUED" * 30, None, True, 1):
            with self.subTest(status=status):
                self.assertTrue(owner3._owner3_status_denied(status))

    def test_real_backend_ack_path_calls_guard(self):
        self.assertIn("_owner3_status_denied(state)", SOURCE.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
