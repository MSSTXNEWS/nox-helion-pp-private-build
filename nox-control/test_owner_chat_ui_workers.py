"""Regression tests for existing owner-only NOX executor status projection.
No OneHost, S03, serving model, process, or HTTP calls.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_chat_ui as ui


class ExistingExecutorClaimsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "status").mkdir()
        (self.root / "state").mkdir()
        override = patch.object(ui, "ROOT", self.root)
        override.start()
        self.addCleanup(override.stop)

    def snapshot(self, workers):
        (self.root / "status/agents_t856u.json").write_text(
            json.dumps({"n": len(workers), "workers": workers}), encoding="utf-8"
        )
        return ui.workers()

    def test_two_idle_workers_without_claims_are_observed(self):
        rows = [
            {"id": "nox-agent-01", "status": "idle"},
            {"id": "nox-agent-02", "status": "idle"},
        ]
        result = self.snapshot(rows)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual([r["task_id"] for r in result["workers"]], [None, None])

    def test_one_busy_claim_two_idle_workers_are_observed(self):
        rows = [
            {"id": "nox-agent-01", "status": "idle"},
            {"id": "nox-agent-02", "status": "busy", "current_task": {"id": "S3-07"}},
            {"id": "nox-agent-03", "status": "idle"},
        ]
        result = self.snapshot(rows)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual([r["task_id"] for r in result["workers"]], [None, "S3-07", None])

    def test_busy_without_claim_id_is_unknown_not_success(self):
        result = self.snapshot([{"id": "nox-agent-01", "status": "busy", "current_task": {}}])
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_duplicate_busy_claims_fail_closed(self):
        result = self.snapshot([
            {"id": "nox-agent-01", "status": "busy", "current_task": {"id": "S2-07"}},
            {"id": "nox-agent-02", "status": "busy", "current_task": {"id": "S2-07"}},
        ])
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_idle_with_unexpected_claim_is_not_accepted(self):
        result = self.snapshot([
            {"id": "nox-agent-01", "status": "idle", "current_task": {"id": "S1-01"}}
        ])
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_model_update_flag_suppresses_stale_busy_claims(self):
        rows = [{"id": "nox-agent-01", "status": "busy",
                 "current_task": {"id": "S2-07"}}]
        flag = self.root / "state/OWNER_MAINTENANCE.flag"
        flag.write_text("owner maintenance")
        result = self.snapshot(rows)
        self.assertEqual(result["state"], "MODEL_UPDATE")
        self.assertEqual(result["owner_maintenance"], "PRESENT")
        self.assertEqual(result["workers"], [])
        self.assertIsNone(result["observed_at"])
        flag.unlink()
        resumed_read_only = ui.workers()
        self.assertEqual(resumed_read_only["state"], "OBSERVED")
        self.assertEqual(resumed_read_only["owner_maintenance"], "ABSENT")

    def test_model_update_flag_overrides_invalid_busy_claim(self):
        (self.root / "state/OWNER_MAINTENANCE.flag").touch()
        result = self.snapshot([{"id": "nox-agent-01", "status": "busy",
                                "current_task": {}}])
        self.assertEqual(result["state"], "MODEL_UPDATE")
        self.assertEqual(result["workers"], [])

    def test_symlinked_maintenance_flag_fails_closed(self):
        target = self.root / "other"
        target.write_text("not an owner maintenance flag")
        (self.root / "state/OWNER_MAINTENANCE.flag").symlink_to(target)
        result = self.snapshot([{"id": "nox-agent-01", "status": "idle"}])
        self.assertEqual(result["state"], "HOLD_MAINTENANCE_UNKNOWN")
        self.assertEqual(result["owner_maintenance"], "UNKNOWN")
        self.assertEqual(result["workers"], [])

    def test_nonregular_maintenance_flag_fails_closed(self):
        (self.root / "state/OWNER_MAINTENANCE.flag").mkdir()
        result = self.snapshot([{"id": "nox-agent-01", "status": "idle"}])
        self.assertEqual(result["state"], "HOLD_MAINTENANCE_UNKNOWN")
        self.assertEqual(result["workers"], [])

    def test_missing_state_directory_does_not_clear_owner_maintenance(self):
        # Previously FileNotFoundError from parent.lstat() incorrectly meant ABSENT.
        (self.root / "state").rmdir()
        result = self.snapshot([{"id": "nox-agent-01", "status": "idle"}])
        self.assertEqual(result["owner_maintenance"], "UNKNOWN")
        self.assertEqual(result["state"], "HOLD_MAINTENANCE_UNKNOWN")
        self.assertEqual(result["workers"], [])

    def test_symlinked_state_directory_cannot_admit_stale_workers(self):
        (self.root / "state").rmdir()
        alternate = self.root / "alternate_state"
        alternate.mkdir()
        (self.root / "state").symlink_to(alternate, target_is_directory=True)
        result = self.snapshot([{"id": "nox-agent-01", "status": "idle"}])
        self.assertEqual(result["owner_maintenance"], "UNKNOWN")
        self.assertEqual(result["state"], "HOLD_MAINTENANCE_UNKNOWN")
        self.assertEqual(result["workers"], [])

    def test_symlinked_status_directory_is_not_a_trusted_snapshot(self):
        rows = [{"id": "nox-agent-01", "status": "idle"}]
        self.snapshot(rows)
        original = self.root / "status"
        relocated = self.root / "moved_status"
        original.rename(relocated)
        original.symlink_to(relocated, target_is_directory=True)
        result = ui.workers()
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertEqual(result["workers"], [])

    def test_fifo_snapshot_is_rejected_without_waiting_for_writer(self):
        import os
        os.mkfifo(self.root / "status/agents_t856u.json")
        result = ui.workers()
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertEqual(result["workers"], [])

    def test_maintenance_transition_during_snapshot_cannot_admit_workers(self):
        rows = [{"id": "nox-agent-01", "status": "idle"}]
        (self.root / "status/agents_t856u.json").write_text(
            json.dumps({"n": 1, "workers": rows}), encoding="utf-8"
        )
        with patch.object(ui, "owner_maintenance_gate", side_effect=["ABSENT", "PRESENT"]):
            result = ui.workers()
        self.assertEqual(result["state"], "MODEL_UPDATE")
        self.assertEqual(result["owner_maintenance"], "PRESENT")
        self.assertEqual(result["workers"], [])
        self.assertIsNone(result["observed_at"])

    def test_owner_scripts_present_maintenance_without_claims(self):
        script = Path(__file__).with_name("owner-chat-ui.js").read_text()
        presence = Path(__file__).with_name("owner-presence.js").read_text()
        self.assertRegex(script, r"state==='MODEL_UPDATE'\s*\?maintenance==='PRESENT'&&rows.length===0")
        self.assertIn("const busy=state==='OBSERVED'?rows.filter(row=>row.status==='busy').length:0", script)
        self.assertIn("online:state==='OBSERVED',busy,state", script)
        self.assertIn("state==='MODEL_UPDATE'", presence)
        self.assertIn("set('updating')", presence)




class ExistingOwnerBridgePartialHtmlTests(unittest.TestCase):
    def test_partial_existing_marked_script_still_loads_all_four_handlers(self):
        raw = ('<html><head><script defer src="/nox-web-v29/owner-presence.js" '
               'data-nox-live-owner="1"></script></head><body></body></html>')
        result = ui.decorate_html(raw, "pc/resonance.html")
        for name in ('nox-v135-resonance-owner-bridge.js',
                     'nox-v137-owner-self-status.js', 'owner-chat-ui.js',
                     'owner-presence.js'):
            self.assertEqual(result.count('src="/nox-web-v29/'+name+'"'), 1)

    def test_unmarked_existing_live_script_is_not_duplicated(self):
        raw = ('<html><head><script src="/nox-web-v29/owner-chat-ui.js">'
               '</script></head><body></body></html>')
        result = ui.decorate_html(raw, "pc/resonance.html")
        self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'), 1)
        self.assertEqual(ui.decorate_html(result, "pc/resonance.html"), result)

    def test_commented_live_script_does_not_hide_required_handler(self):
        raw = ('<html><head><!-- disabled <script src="/nox-web-v29/owner-chat-ui.js">'
               '</script> --></head><body></body></html>')
        result = ui.decorate_html(raw, "pc/resonance.html")
        expected = ('<script defer src="/nox-web-v29/owner-chat-ui.js" '
                    'data-nox-live-owner="1"></script>')
        self.assertIn(expected, result)
        self.assertEqual(ui.decorate_html(result, "pc/resonance.html"), result)

    def test_commented_meta_does_not_hide_current_live_build(self):
        raw = ('<html><head><!-- <meta name="nox-live-build" content="old"> -->'
               '</head><body></body></html>')
        result = ui.decorate_html(raw, "pc/resonance.html")
        self.assertIn('<meta name="nox-live-build" content="' + ui.BUILD + '">', result)
        self.assertEqual(ui.decorate_html(result, "pc/resonance.html"), result)

    def test_unrelated_marked_script_cannot_suppress_live_owner_bridge(self):
        raw = ('<html><head><script data-nox-live-owner="1" '
               'src="/nox-web-v29/unrelated.js"></script></head></html>')
        result = ui.decorate_html(raw, "pc/resonance.html")
        self.assertEqual(result.count('src="/nox-web-v29/nox-v135-resonance-owner-bridge.js"'), 1)
        self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'), 1)

if __name__ == "__main__":
    unittest.main()
