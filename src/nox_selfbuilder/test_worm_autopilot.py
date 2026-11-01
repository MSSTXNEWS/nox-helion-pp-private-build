"""Simulate existing owner boot/idle callbacks, without model, network or GUI."""
import unittest
from datetime import datetime, timedelta, timezone
from src.nox_selfbuilder.worms import WormSwarm
from src.nox_selfbuilder.worm_autopilot import WormAutopilot

HEAD = "c" * 40
NOW = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)


class AutonomousBootTests(unittest.TestCase):
    def setUp(self):
        self.reads = []
        self.saved = []
        self.grants = {"worm.autonomy.toggle", "worm.autonomy.read"}
        self.policy = {}
        self.stop_requested = False

        def provider(task):
            self.reads.append(task.task_id)
            return []
        self.swarm = WormSwarm(
            provider_map={"github_api": provider},
            source_hosts={"github_api": "github.com"},
            admit=lambda _session, action: action in self.grants,
            persist=lambda _session, receipt: True)
        self.engine = WormAutopilot(
            native_signed_policy=lambda _session: dict(self.policy),
            source_head=lambda: HEAD,
            swarm=self.swarm,
            native_stop=lambda: self.stop_requested,
            s03_append_readback=lambda _session, data: self.saved.append(data) or True)

    def native_policy(self):
        self.policy = {
            "schema": "NOX-NATIVE-WORMS-POLICY-v1",
            "signed_by_native_owner": True,
            "allow_autonomous_public_research": True,
            "approved_source_head": HEAD,
            "expires_at_utc": (NOW+timedelta(days=1)).isoformat(),
        }

    def test_boot_creates_240_initiatives_with_no_network_when_no_native_policy(self):
        receipt = self.engine.boot("owner", now=NOW)
        self.assertEqual(receipt["planned_tasks"], 240)
        self.assertEqual(receipt["state"], "NATIVE_POLICY_NOT_CONFIGURED")
        self.assertEqual(self.reads, [])
        self.assertEqual(self.saved, [])

    def test_owner_signed_policy_boot_saves_once_and_existing_idle_loop_fetches(self):
        self.native_policy()
        first = self.engine.boot("owner", now=NOW)
        self.assertEqual(first["state"], "RESEARCH_READY_FOR_EXISTING_IDLE_TICK")
        self.assertFalse(first["research_started"])
        self.assertEqual(len(self.saved), 1)
        self.assertFalse(self.reads)
        self.engine.boot("owner", now=NOW)
        self.assertEqual(len(self.saved), 1)
        result = self.engine.tick("owner", now=NOW)
        self.assertEqual(result["web_requests_attempted"], 4)
        self.assertEqual(len(self.reads), 4)

    def test_native_stop_prevents_boot_or_idle(self):
        self.native_policy()
        self.stop_requested = True
        self.assertEqual(self.engine.boot("owner", now=NOW)["state"],
                         "STOPPED_BEFORE_BOOT")
        self.assertFalse(self.saved)
        self.stop_requested = False
        self.engine.boot("owner", now=NOW)
        self.stop_requested = True
        self.assertEqual(self.engine.tick("owner", now=NOW)["reason"],
                         "STOP_OR_SCOPE_HOLD")
        self.assertFalse(self.reads)

    def test_revoked_or_expired_policy_blocks(self):
        self.native_policy()
        self.engine.boot("owner", now=NOW)
        self.policy["allow_autonomous_public_research"] = False
        self.assertEqual(self.engine.tick("owner", now=NOW)["reason"],
                         "NATIVE_POLICY_REVOKED")
        self.assertFalse(self.reads)

    def test_incomplete_provider_permissions_cannot_promote_source(self):
        self.native_policy()
        self.grants.remove("worm.autonomy.toggle")
        receipt = self.engine.boot("owner", now=NOW)
        self.assertEqual(receipt["state"], "NATIVE_WORM_RESEARCH_AUTH_HOLD")
        self.assertEqual(self.reads, [])

    def test_scope_switch_is_not_cross_tenant(self):
        self.native_policy()
        self.engine.boot("owner", now=NOW)
        self.assertEqual(self.engine.boot("another-tenant", now=NOW)["state"],
                         "NATIVE_SCOPE_CHANGED")
        self.assertEqual(self.engine.tick("another-tenant", now=NOW)["reason"],
                         "STOP_OR_SCOPE_HOLD")


if __name__ == "__main__":
    unittest.main()
