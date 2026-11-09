"""Genuine role initiative tests, no network, model weights or second LLM."""
import unittest
from datetime import datetime, timezone

from src.nox_selfbuilder.worms import plan_day, inspect_evidence, WormHold
from src.nox_selfbuilder.worm_idea_loop import NativeIdeaLoop

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


def observed(core):
    task = next(t for t in plan_day(NOW) if t.core_id == core)
    return inspect_evidence(task, {
        "url": "https://github.com/researched/feature" + core.lower(),
        "title": "Useful source for " + core,
        "excerpt": "Verified citation from approved provider for feature reuse",
        "source_id": "gh:" + core,
        "license": "MIT",
    }, source_host="github.com")


def fake_idea(brief):
    src = brief["sources"][0]
    return [{
        "source_sha256": src["source_sha256"], "kind": "skill",
        "target_id": "nox.curated-skill", "description":
        "Reuse a verified skill candidate to improve existing NOX.",
        "benefit": 5, "readiness": 4, "reuse": 5, "risk": 1,
        "effort_minutes": 10,
    }]


class AutonomousIdeaTests(unittest.TestCase):
    def setUp(self):
        self.rows = [observed("ATLAS"), observed("FORGE"), observed("NEXUS")]
        self.grants = {"worm.brainstorm.read", "worm.candidate.persist"}
        self.messages = []
        self.receipts = []
        self.stopped = False
        def model(brief):
            self.messages.append(brief)
            return fake_idea(brief)
        self.agent = NativeIdeaLoop(
            authorized=lambda _session, action: action in self.grants,
            source_head=lambda: HEAD,
            s03_verified_observations=lambda _session: list(self.rows),
            p02_model_propose=model,
            s03_save_candidate_readback=lambda _session, row:
                self.receipts.append(row) or True,
            native_stop=lambda: self.stopped)

    def test_roles_invent_without_user_writing_ideas(self):
        status = self.agent.tick("owner", now=NOW)
        self.assertEqual(status["p02_calls"], 2)
        self.assertEqual(len(self.receipts), 2)
        self.assertEqual(self.messages[0]["role"], "ATLAS")
        self.assertEqual(self.messages[1]["role"], "NEXUS")
        self.assertTrue(all(x["state"] == "SANDBOX_CANDIDATE_REVIEW_REQUIRED"
                            for x in self.receipts))
        self.assertFalse(status["weights_updated"])

    def test_dedup_across_idle_ticks(self):
        self.agent.tick("owner", now=NOW)
        self.agent.tick("owner", now=NOW)
        self.agent.tick("owner", now=NOW)
        self.assertEqual(len(self.messages), 3)
        self.assertEqual(len(self.receipts), 3)

    def test_native_stop_or_policy_revoke_prevents_model(self):
        self.stopped = True
        self.assertEqual(self.agent.tick("owner", now=NOW)["reason"],
                         "NATIVE_STOP_OR_POLICY_DENIED")
        self.stopped = False
        self.grants.remove("worm.brainstorm.read")
        self.agent.tick("owner", now=NOW)
        self.assertEqual(self.messages, [])

    def test_empty_memory_does_not_fake_brainstorm(self):
        self.rows.clear()
        state = self.agent.tick("owner", now=NOW)
        self.assertEqual(state["reason"], "NO_VERIFIED_EVIDENCE_YET")
        self.assertEqual(state["p02_calls"], 0)

    def test_persist_requires_real_native_s03_ack(self):
        self.grants.remove("worm.candidate.persist")
        self.agent.tick("owner", now=NOW)
        self.assertEqual(self.receipts, [])
        self.assertEqual(len(self.messages), 2)

    def test_bad_s03_scope_rejected(self):
        self.rows = [{"schema": "fake", "core_id": "ATLAS"}]
        with self.assertRaises(WormHold):
            self.agent.tick("owner", now=NOW)


    def test_unknown_stop_is_fail_closed(self):
        self.stopped = None
        self.assertEqual(self.agent.tick("owner", now=NOW)["reason"],
                         "NATIVE_STOP_OR_POLICY_DENIED")
        self.assertEqual(self.messages, [])

    def test_scope_change_requires_another_native_runtime(self):
        self.agent.tick("owner", now=NOW)
        with self.assertRaisesRegex(WormHold, "SESSION_SCOPE_CHANGED"):
            self.agent.tick("other-owner", now=NOW)

    def test_stop_after_p02_cannot_save_or_consume_dedupe(self):
        def revoking_model(brief):
            self.stopped=True
            return fake_idea(brief)
        self.agent._model=revoking_model
        result=self.agent.tick("owner", now=NOW)
        self.assertIn("AFTER_P02", result["reason"])
        self.assertEqual(self.receipts, [])
        self.assertEqual(result["distinct_p02_groups"], 0)

    def test_s03_stop_after_commit_never_reports_saved(self):
        def save_then_stop(session, row):
            self.receipts.append(row)
            self.stopped=True
            return True
        self.agent._save=save_then_stop
        result=self.agent.tick("owner",now=NOW)
        self.assertEqual(result["reason"],"S03_COMMIT_AFTER_REVOKE_READBACK_REQUIRED")
        self.assertEqual(result["review_candidates_saved"],0)
        self.assertEqual(result["distinct_p02_groups"],0)

if __name__ == "__main__":
    unittest.main()
