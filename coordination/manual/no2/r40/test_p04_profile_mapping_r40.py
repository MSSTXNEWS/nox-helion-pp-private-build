"""NOX V16 T08 R40: MAX UI preset must be normalized to the original QLoRA worker.

This supersedes R36 test_p04_training_profile_alignment_r36.py, which
incorrectly required UI and worker profile-name sets to be identical.
Execute only in read-only source checkout: python -m unittest -v
coordination/manual/no2/r40/test_p04_profile_mapping_r40.py
No CUDA, model weights, process launch, network, or product mutation.
"""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "proposals/NOX-PACK01-50/p04_owner_training_port.py"
WORKER = ROOT / "Packages/P04/train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_r40_owner", OWNER)
if spec is None or spec.loader is None:
    raise RuntimeError("NOX_P04_OWNER_CODE_MISSING")
owner = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = owner
spec.loader.exec_module(owner)
RUN_ID = "NOX-P04-R40"

def existing_worker_profiles():
    tree = ast.parse(WORKER.read_text("utf-8"))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PROFILES" for t in n.targets
        ):
            return set(ast.literal_eval(n.value))
    raise RuntimeError("ORIGINAL_PROFILES_MISSING")

def make_plan(profile=None):
    params = [
        ("--model", "/trusted/model"),
        ("--model-lock", "/trusted/model-lock"),
        ("--model-revision", "a" * 40),
        ("--dataset-manifest", "/trusted/dataset"),
        ("--rights-verifier", "/trusted/rights"),
        ("--train-jsonl", "/trusted/train"),
        ("--holdout-jsonl", "/trusted/holdout"),
        ("--output-dir", "/trusted/out"),
        ("--events-jsonl", "/trusted/events"),
        ("--run-id", RUN_ID),
        ("--task-id", RUN_ID),
        ("--stop-marker", "/trusted/stop"),
    ]
    if profile is not None:
        params.append(("--profile", profile))
    flat = tuple(s for row in params for s in row)
    return owner.NativeQLoRAPlan(Path("/trusted/python"), Path("/trusted/train_qlora.py"),
                                "b" * 64, flat, RUN_ID)

def normalized_profile(plan):
    arguments = owner._plan_args(plan)
    pairs = dict(zip(arguments[::2], arguments[1::2]))
    return pairs.get("--profile", "BALANCED")

class ProfileMapQA(unittest.TestCase):
    def test_max_is_converted_to_existing_worker_intensive(self):
        plan = make_plan("MAX")
        self.assertEqual(normalized_profile(plan), "INTENSIVE")
        self.assertIn(normalized_profile(plan), existing_worker_profiles())
        # Immutable native user's approved UI intent remains untouched.
        self.assertEqual(dict(zip(plan.argv_pairs[::2], plan.argv_pairs[1::2]))["--profile"], "MAX")

    def test_eco_unchanged(self):
        self.assertEqual(normalized_profile(make_plan("ECO")), "ECO")

    def test_balanced_unchanged(self):
        self.assertEqual(normalized_profile(make_plan("BALANCED")), "BALANCED")

    def test_default_balanced_unchanged(self):
        self.assertEqual(normalized_profile(make_plan()), "BALANCED")

    def test_arbitrary_unapproved_profile_denied(self):
        with self.assertRaises(owner.P04Hold):
            normalized_profile(make_plan("EXTREME"))

    def test_worker_preserves_original_three_profiles(self):
        self.assertEqual(existing_worker_profiles(), {"ECO", "BALANCED", "INTENSIVE"})

if __name__ == "__main__":
    unittest.main()
