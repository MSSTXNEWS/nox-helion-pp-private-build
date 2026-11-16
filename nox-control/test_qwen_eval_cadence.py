#!/usr/bin/env python3
"""Source-only regressions for NOX Qwen holdout cadence; NO native actions."""
import ast
import math
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("qwen_student_training_entry.py")
GUARD = Path(__file__).with_name("owner_qwen_training_guard.py")


class Hold(Exception):
    pass


def isolated_decision():
    """Compile ONLY the checked pure source function, not model dependencies."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == "holdout_evaluation_due"]
    if len(nodes) != 1:
        raise AssertionError("ONE_SOURCE_HOLDOUT_SCHEDULER_REQUIRED")
    namespace = {"math": math, "Hold": Hold}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["holdout_evaluation_due"], tree


class EvaluationCadenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.due, cls.tree = isolated_decision()

    def test_every_five_successful_updates_has_fresh_holdout(self):
        for step in range(6, 31):
            self.assertEqual(self.due(step, 1000, 2.0), step % 5 == 0, step)
        self.assertTrue(self.due(1000, 1000, 0.0))

    def test_time_budget_fallback_is_not_reset_away(self):
        self.assertFalse(self.due(8, 1000, 299.9))
        self.assertTrue(self.due(8, 1000, 300))
        self.assertTrue(self.due(8, 1000, 301))

    def test_invalid_counters_fail_closed(self):
        for row in [(-1, 1000, 0), (1001, 1000, 0), (7, 5, 0),
                    (True, 1000, 0), (7, 1000, float("nan")),
                    (7, 1000, -1)]:
            with self.subTest(row=row), self.assertRaises(Hold):
                self.due(*row)

    def test_live_training_loop_uses_tested_policy(self):
        calls = [node for node in ast.walk(self.tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "holdout_evaluation_due"]
        self.assertEqual(len(calls), 1)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if not reason and evaluation_due:", source)
        self.assertIn("state[\"holdout_evaluated_successful_total\"] = state[\"successful_total\"]", source)
        self.assertIn("checkpoint, record = save_checkpoint(", source)

    def test_existing_guard_stale_limit_is_not_weakened(self):
        guard = GUARD.read_text(encoding="utf-8")
        self.assertIn("good - evaluated >= p['stale_successful_updates']", guard)
        self.assertIn("reason = 'EVALUATION_STALE'", guard)
        self.assertIn("if p.get('inhibit') is True:", guard)
        # The trainer checks at <= 5-update intervals while policy retains its
        # existing fail-closed stale gate and owner STOP/lease requirements.
        self.assertTrue(self.due(15, 1000, 0.0))


if __name__ == "__main__":
    unittest.main()
