"""Independent portable contract tests for the additive five-block native adapter."""
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nox_fastpack.five_blocks import dispatch_five


class DummyOwner:
    def __init__(self, root):
        self.root = Path(root)
        self._stop_event = threading.Event()

    def _project(self, project_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", project_id):
            raise ValueError("Existing project ID restriction")
        result = self.root / project_id
        result.mkdir(exist_ok=True)
        return result


class FiveBlockContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = DummyOwner(self.temp.name)

    def event(self, block, kind, text="User-authored idea", source_url=""):
        return dispatch_five(self.owner, {
            "action": "cs5_append", "project_id": "creative01",
            "block": block, "kind": kind, "text": text, "source_url": source_url
        })

    def test_five_blocks_and_no_fake_runtime(self):
        result = dispatch_five(self.owner, {"action": "cs5_overview"})
        self.assertEqual(sorted(result["blocks"]), ["B01", "B02", "B03", "B04", "B05"])
        self.assertEqual(result["publication"], "NO_EXTERNAL_PUBLISHER_CONNECTED")

    def test_project_chain_and_readback(self):
        self.event("B01", "hypothesis", source_url="https://example.org/source")
        self.event("B02", "idea")
        self.event("B03", "production")
        self.event("B04", "model_note")
        self.event("B05", "brand")
        result = dispatch_five(self.owner, {"action": "cs5_list", "project_id": "creative01"})
        self.assertEqual(result["count"], 5)
        self.assertEqual([x["block"] for x in result["events"]], ["B01","B02","B03","B04","B05"])
        self.assertEqual(result["events"][1]["prev_sha256"], result["events"][0]["sha256"])
        self.assertEqual(result["events"][0]["evidence_status"], "HYPOTHESIS")

    def test_external_receipt_is_unverified(self):
        result = self.event("B05", "receipt", "Provider claim, not attested")
        self.assertEqual(result["evidence_status"], "REPORTED_UNVERIFIED")

    def test_stop_is_fail_closed(self):
        self.owner._stop_event.set()
        with self.assertRaisesRegex(ValueError, "CS5_STOP_ACTIVE"):
            self.event("B02", "idea")
        self.assertEqual(dispatch_five(self.owner, {
            "action": "cs5_list", "project_id": "creative01"})["count"], 0)

    def test_invalid_record_and_url_rejected(self):
        with self.assertRaisesRegex(ValueError, "CS5_SOURCE_URL_HOLD"):
            self.event("B01", "research", source_url="file:///private.txt")
        with self.assertRaisesRegex(ValueError, "CS5_BLOCK_KIND_HOLD"):
            self.event("B05", "hypothesis")
        with self.assertRaisesRegex(ValueError, "CS5_TEXT_LIMIT"):
            self.event("B02", "idea", text="")

    def test_tamper_proof_readback(self):
        self.event("B02", "bible")
        path = Path(self.temp.name) / "creative01" / "cs5_project_events.json"
        state = json.loads(path.read_text())
        state["events"][0]["text"] = "tampered"
        path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "CS5_EVENT_CHAIN_HOLD"):
            dispatch_five(self.owner, {"action": "cs5_list", "project_id": "creative01"})

    def test_no_project_escape(self):
        with self.assertRaises(ValueError):
            dispatch_five(self.owner, {"action":"cs5_list","project_id":"../../other"})

    def test_linked_file_is_rejected(self):
        path = Path(self.temp.name) / "creative01"
        path.mkdir()
        target = Path(self.temp.name) / "sensitive.json"
        target.write_text("{}")
        try:
            (path / "cs5_project_events.json").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available on this platform")
        with self.assertRaisesRegex(ValueError, "CS5_PROJECT_LINK_HOLD"):
            dispatch_five(self.owner, {"action":"cs5_list","project_id":"creative01"})


if __name__ == "__main__":
    unittest.main()
