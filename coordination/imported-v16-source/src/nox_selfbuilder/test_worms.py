"""Bounded native-role research tests. No network, model or database required."""
import unittest
from datetime import datetime, timezone

from src.nox_selfbuilder.worms import (
    ROLES, TOPICS, WormHold, WormSwarm, inspect_evidence, plan_day, role_mood,
)


class WormTests(unittest.TestCase):
    def setUp(self):
        self.source = {"url": "https://github.com/example/repo",
                       "title": "Example module", "excerpt": "Verified listing only",
                       "source_id": "gh/example/repo", "license": "REVIEW_REQUIRED"}
        self.persisted = []
        self.grants = {"worm.autonomy.toggle", "worm.autonomy.read"}
        self.calls = []
        def provider(task):
            self.calls.append(task)
            return [dict(self.source)]
        def admit(_session, action):
            return action in self.grants
        def persist(_session, finding):
            self.persisted.append(finding)
            return True
        self.engine = WormSwarm(
            provider_map={"github_api": provider}, admit=admit, persist=persist,
            source_hosts={"github_api": "github.com"}, max_fetches_day=3)
        self.now = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)

    def test_240_unique_role_initiatives_without_duplicates(self):
        tasks = plan_day(self.now)
        self.assertEqual(len(tasks), 240)
        self.assertEqual(len({x.task_id for x in tasks}), 240)
        self.assertEqual(set(x.core_id for x in tasks), set(ROLES))
        self.assertEqual(set(x.topic for x in tasks), set(TOPICS))
        self.assertEqual(len(set(x.lens for x in tasks)), 5)

    def test_default_disabled_never_fetches_or_writes(self):
        state = self.engine.tick("session", now=self.now)
        self.assertEqual(state["status"], "OFF")
        self.assertFalse(self.calls)
        self.assertFalse(self.persisted)

    def test_explicit_owner_enable_and_real_source_to_s03(self):
        self.engine.set_enabled("session", True)
        state = self.engine.tick("session", now=self.now, max_tasks=2)
        self.assertEqual(state["web_requests_attempted"], 2)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(state["source_observations_saved"], 1)
        self.assertEqual(self.persisted[0]["status"], "SOURCE_OBSERVED_REVIEW_REQUIRED")
        self.assertFalse(self.persisted[0]["code_executed"])
        self.assertFalse(self.persisted[0]["weights_updated"])
        self.assertEqual(len(self.persisted[0]["source_sha256"]), 64)

    def test_quota_and_role_scheduler_do_not_forge_hundreds_of_fetches(self):
        self.engine.set_enabled("session", True)
        for _ in range(8):
            state = self.engine.tick("session", now=self.now, max_tasks=4)
        self.assertEqual(state["web_requests_attempted"], 3)
        self.assertLessEqual(state["source_observations_saved"], 3)
        self.assertEqual(state["assignments_possible_per_day"], 240)

    def test_owner_revoke_stops_new_requests(self):
        self.engine.set_enabled("session", True)
        self.engine.tick("session", now=self.now, max_tasks=1)
        self.engine.set_enabled("session", False)
        after = len(self.calls)
        self.engine.tick("session", now=self.now)
        self.assertEqual(len(self.calls), after)
        self.assertEqual(role_mood(self.engine.status())["focus"], "RESTING")

    def test_admission_revoked_after_enable_denies_tick(self):
        self.engine.set_enabled("session", True)
        self.grants.remove("worm.autonomy.read")
        self.assertEqual(self.engine.tick("session", now=self.now)["reason"],
                         "NATIVE_REVOKED")
        self.assertFalse(self.calls)

    def test_external_untrusted_url_script_and_fields_rejected(self):
        task = plan_day(self.now)[0]
        for url in ("http://github.com/x", "https://evil.test/x",
                    "https://github.com:8443/x", "https://user@github.com/a"):
            with self.subTest(url=url):
                with self.assertRaises(WormHold):
                    inspect_evidence(task, {**self.source, "url": url}, source_host="github.com")
        for row in ({**self.source, "excerpt": "<script>run()</script>"},
                    {**self.source, "shell_command": "rm -rf /"}):
            with self.assertRaises(WormHold):
                inspect_evidence(task, row, source_host="github.com")

    def test_tiktok_research_is_not_public_without_approved_provider(self):
        self.engine.set_enabled("session", True)
        state = self.engine.tick("session", now=self.now, max_tasks=1)
        self.assertEqual(state["web_requests_attempted"], 1)
        self.assertTrue(all(x.provider != "tiktok_approved_api" for x in self.calls))

    def test_no_source_persist_without_actual_readback(self):
        e = WormSwarm(provider_map={"github_api": lambda _:[self.source]},
             source_hosts={"github_api": "github.com"},
             admit=lambda _s, _a: True, persist=lambda _s, _f: False)
        e.set_enabled("session", True)
        result = e.tick("session", now=self.now, max_tasks=1)
        self.assertEqual(result["source_observations_saved"], 0)
        self.assertEqual(result["errors"], 1)

    def test_disabled_provider_bad_task_quotas_fail_closed(self):
        with self.assertRaises(WormHold):
            WormSwarm(provider_map={"unknown": lambda _: []},
                source_hosts={"unknown": "github.com"},
                admit=lambda *_: True, persist=lambda *_: True)
        with self.assertRaises(WormHold):
            plan_day(self.now, roles=["HACKER"])
        with self.assertRaises(WormHold):
            self.engine.set_enabled("session", "yes")
        with self.assertRaises(WormHold):
            self.engine.tick("session", now=self.now, max_tasks=99)


if __name__ == "__main__":
    unittest.main()
