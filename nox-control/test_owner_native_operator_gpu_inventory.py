import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import owner_native_operator as operator


class OwnerGpuInventoryOperatorTests(unittest.TestCase):
    def test_action_route_and_embedded_payload_blob_pin(self):
        self.assertEqual(operator.FILES["gpu_inventory"],
                         "nox-control/owner_native_gpu_inventory.py")
        payload = operator._load_action_payload("gpu_inventory")
        self.assertIn('NOX_MAINT_GPU_INVENTORY_COMPLETE=true', payload)
        self.assertEqual(len(operator.GPU_INVENTORY_BLOB_SHA), 40)
        with patch.object(operator.Path, "read_text", return_value=payload + "# changed\n"):
            with self.assertRaisesRegex(RuntimeError, "HOLD_GPU_INVENTORY_PAYLOAD_PIN"):
                operator._load_action_payload("gpu_inventory")

    def test_exact_owner_request_and_source_checkout_are_required(self):
        sha = "a" * 40
        event = {
            "repository": {"owner": {"id": operator.OWNER_ID}},
            "issue": {"number": 256},
            "sender": {"id": operator.OWNER_ID},
            "comment": {
                "id": 7000000000,
                "user": {"id": operator.OWNER_ID},
                "author_association": "OWNER",
                "body": f"/nox-maintain {operator.INSTANCE} {sha} gpu_inventory",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_REPOSITORY": operator.REPO,
                "GITHUB_EVENT_NAME": "issue_comment",
                "NOX_PINNED_SOURCE_SHA": sha,
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("owner_native_operator.subprocess.check_output",
                           return_value=sha + "\n"):
                    self.assertEqual(operator.authorize_event("gpu_inventory"), 7000000000)
                event["comment"]["body"] = f"/nox-maintain {operator.INSTANCE} {sha} audit"
                event_path.write_text(json.dumps(event), encoding="utf-8")
                with patch("owner_native_operator.subprocess.check_output",
                           return_value=sha + "\n"):
                    with self.assertRaisesRegex(RuntimeError, "HOLD_EXACT_OWNER_COMMAND"):
                        operator.authorize_event("gpu_inventory")


if __name__ == "__main__":
    unittest.main(verbosity=2)
