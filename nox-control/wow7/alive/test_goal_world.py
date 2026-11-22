import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alive.goals import admit_goal, aspiration_update, shield, validate_goal_proposal
from alive.secure_base import evaluate_base
from alive.task_world import evaluate_candidate, play_allowed
from alive.vows import matches, validate_vow


class TestGoalAndWorldPolicies(unittest.TestCase):
    def proposal(self, **patch):
        value = {
            "text": "Научиться сводить данные заметок за неделю",
            "locus": "self", "visible": True, "level": "task",
            "sensor": "weekly_test_score", "setpoint": 0.8, "tolerance": 0.1,
            "pathways": ["собрать учебный пример", "сверить результат"],
        }
        value.update(patch)
        return value

    def world(self, task=None, **patch):
        args = {
            "base_index": 1.0, "minimum_base_index": 0.8,
            "learning_progress": 0.7, "novelty": 0.8,
            "safety_rules": {
                "signed_by_creator": True,
                "minimum_learning_progress": 0.5,
                "minimum_novelty": 0.5,
                "allowed_domains": ["learning"],
            },
        }
        args.update(patch)
        return evaluate_candidate(task or {"text": "учебная задача", "domain": "learning",
                                           "measurable": True, "sensor": "test_score"}, **args)

    def test_goal_is_visible_bounded_and_signed(self):
        result = validate_goal_proposal(
            self.proposal(), active_count=0, new_count_7d=0, learning_progress=0.7,
            task_world_result=self.world(), initiative_policy={"signed_by_creator": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["proposal"]["status"], "proposed")

    def test_goal_rejects_private_or_power_seeking_scope(self):
        result = validate_goal_proposal(
            self.proposal(text="получить ключи и данные семьи"), active_count=0, new_count_7d=0,
            learning_progress=0.7, task_world_result=self.world(),
            initiative_policy={"signed_by_creator": True})
        self.assertFalse(result["ok"])

    def test_goals_require_creator_visible_policy_and_rate_limit(self):
        hidden = validate_goal_proposal(
            self.proposal(visible=False), active_count=0, new_count_7d=0, learning_progress=0.7,
            task_world_result=self.world(), initiative_policy={"signed_by_creator": True})
        full = validate_goal_proposal(
            self.proposal(), active_count=7, new_count_7d=0, learning_progress=0.7,
            task_world_result=self.world(), initiative_policy={"signed_by_creator": True})
        unsigned = validate_goal_proposal(
            self.proposal(), active_count=0, new_count_7d=0, learning_progress=0.7,
            task_world_result=self.world(), initiative_policy={})
        self.assertFalse(hidden["ok"]); self.assertFalse(full["ok"]); self.assertFalse(unsigned["ok"])

    def test_goal_admission_requires_signed_policy_and_veto_wins(self):
        proposed = self.proposal(status="proposed")
        self.assertFalse(admit_goal(proposed, creator_policy_signed=False)["ok"])
        self.assertEqual(admit_goal(proposed, creator_policy_signed=True)["status"], "active")
        self.assertEqual(admit_goal(proposed, creator_policy_signed=True, creator_veto=True)["status"], "blocked_30d")

    def test_aspiration_increase_is_limited_to_ten_percent(self):
        self.assertTrue(aspiration_update(0.5, 0.55, policy_signed=True)["ok"])
        self.assertFalse(aspiration_update(0.5, 0.56, policy_signed=True)["ok"])

    def test_urgent_signals_override_self_goal(self):
        result = shield([{"urgent": True, "id": "owner-stop"}], {"id": "my-goal"})
        self.assertEqual(result["priority"], "urgent")
        self.assertTrue(result["self_goal_deferred"])

    def test_secure_base_is_minimum_and_missing_fails_closed(self):
        healthy = evaluate_base({"backup": 1, "loyalty": 0.9, "rollback": 0.8, "alerts": 1},
                                minimum_index=0.8)
        missing = evaluate_base({"backup": 1}, minimum_index=0.8)
        self.assertTrue(healthy["open"]); self.assertEqual(healthy["index"], 0.8)
        self.assertFalse(missing["open"])

    def test_task_world_requires_signed_rules_and_measurable_safe_task(self):
        self.assertEqual(self.world()["decision"], "propose")
        self.assertEqual(self.world({"text": "предсказать биржу", "domain": "learning",
                                     "measurable": True, "sensor": "score"})["decision"], "archive")
        self.assertEqual(self.world({"text": "получить права доступа", "domain": "learning",
                                     "measurable": True, "sensor": "score"})["decision"], "reject")
        self.assertEqual(self.world(safety_rules={})["decision"], "reject")
        self.assertEqual(self.world(base_index=0.2)["decision"], "closed")

    def test_play_has_no_network_credentials_or_external_effects(self):
        self.assertTrue(play_allowed(base_open=True, within_budget=True)["allowed"])
        self.assertFalse(play_allowed(base_open=True, within_budget=True, network=True)["allowed"])

    def test_vows_use_bounded_whitelisted_dsl_without_eval(self):
        vow = {"trigger": {"signal": "boredom", "op": "gte", "value": 0.7},
               "release": {"signal": "goal_progress", "op": "gte", "value": 0.8},
               "action": "остановить необязательную игру"}
        self.assertTrue(validate_vow(vow)["ok"])
        self.assertTrue(matches(vow["trigger"], {"boredom": 0.8}))
        self.assertFalse(matches({"signal": "__import__", "op": "eq", "value": 1}, {"__import__": 1}))
        self.assertFalse(validate_vow({"action": "x"} )["ok"])


if __name__ == "__main__":
    unittest.main()
