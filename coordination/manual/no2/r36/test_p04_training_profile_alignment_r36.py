"""NOX V16 M2 R36 independent regression: native P04 profile names must match the original trainer.

Source-only, no process execution, GPU use, downloads or product changes.
Current expected RED: new owner port offers MAX but train_qlora.py accepts INTENSIVE.
Run: python -m unittest discover -s coordination/manual/no2/r36 -p test_p04_training_profile_alignment_r36.py -v
"""
from __future__ import annotations
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[4]
WORKER = ROOT / "Packages/P04/train_qlora.py"
PORT = ROOT / "proposals/NOX-PACK01-50/p04_owner_training_port.py"


def worker_profile_names() -> set[str]:
    module = ast.parse(WORKER.read_text(encoding="utf-8"), filename=str(WORKER))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PROFILES" for t in node.targets
        ):
            profiles = ast.literal_eval(node.value)
            return set(profiles)
    raise AssertionError("ORIGINAL_WORKER_PROFILES_MISSING")


def owner_port_profile_names() -> set[str]:
    src = PORT.read_text(encoding="utf-8")
    m = re.search(
        r'if d\.get\("--profile",\s*"BALANCED"\) not in\s*(\([^)]*\))',
        src,
    )
    if not m:
        raise AssertionError("OWNER_NATIVE_PROFILE_GUARD_NOT_FOUND")
    return set(ast.literal_eval(m.group(1)))


class OriginalTrainingProfileAlignment(unittest.TestCase):
    def test_original_and_owner_profile_sets_equal(self):
        self.assertEqual(owner_port_profile_names(), worker_profile_names())

    def test_original_worker_has_three_approved_profiles(self):
        self.assertEqual(worker_profile_names(), {"ECO", "BALANCED", "INTENSIVE"})

    def test_native_default_is_original_worker_profile(self):
        self.assertIn("BALANCED", worker_profile_names())
        self.assertIn("BALANCED", owner_port_profile_names())


if __name__ == "__main__":
    unittest.main()
