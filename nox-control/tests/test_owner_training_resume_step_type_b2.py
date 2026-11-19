"""B2/4A02: source-isolated regression for optimizer checkpoint step provenance.

Extract the exact functions under test from the pinned owner script without
importing its maintenance entrypoint or starting a service.
"""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import types
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "owner_training_resume.py"
FN_NAMES = {"read_json", "file_sha", "verify_paused_result"}


def load_pinned_verifier(output):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in FN_NAMES]
    if {node.name for node in nodes} != FN_NAMES:
        raise AssertionError("HOLD_EXACT_OWNER_VERIFIER_MISSING")
    namespace = {
        "Path": Path, "hashlib": hashlib, "json": json, "math": math,
        "re": re, "OUTPUT": output, "NATIVE_SHA": "a" * 64,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace


class CheckpointStepProvenance(unittest.TestCase):
    def test_step_types_fail_closed_even_with_matching_file_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            verifier = load_pinned_verifier(out)
            cp = out / "checkpoint-1"
            cp.mkdir()
            (cp / "adapter_model.safetensors").write_bytes(b"bounded-test-tensor")
            state = cp / "trainer_state.json"
            state.write_text('{"global_step": 1}', encoding="utf-8")
            names = ("adapter_model.safetensors", "trainer_state.json")
            hashes = {name: verifier["file_sha"](cp / name) for name in names}
            receipt = {
                "global_step": 1, "state": "CHECKPOINTED_OWNER_STOP",
                "native_sha256": "a" * 64,
                "successful_optimizer_steps": 1,
                "adapter_delta_verified": True, "loss": 0.4,
                "before_tensor_sha256": "b" * 64,
                "after_tensor_sha256": "c" * 64,
                "checkpoint": {
                    "path": str(cp), "global_step": 1,
                    "files_sha256": hashes,
                },
            }
            helper = types.SimpleNamespace(CHECKPOINT_NAMES=names)
            check = verifier["verify_paused_result"]
            self.assertTrue(check(helper, receipt))

            # A single optimizer step cannot honestly claim two successful steps.
            impossible_count = copy.deepcopy(receipt)
            impossible_count["successful_optimizer_steps"] = 2
            with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_OPTIMIZER_RECEIPT"):
                check(helper, impossible_count)

            # Python bool is an int subclass: True == 1 must not verify a step.
            wrong_receipt = copy.deepcopy(receipt)
            wrong_receipt["checkpoint"]["global_step"] = True
            with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_CHECKPOINT_SCOPE"):
                check(helper, wrong_receipt)

            # Fully rehash the edited trainer_state: this must reach the
            # semantic step-type check, not fail at the earlier hash gate.
            state.write_text('{"global_step": true}', encoding="utf-8")
            wrong_state = copy.deepcopy(receipt)
            wrong_state["checkpoint"]["files_sha256"]["trainer_state.json"] = (
                verifier["file_sha"](state)
            )
            with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_CHECKPOINT_STEP"):
                check(helper, wrong_state)

            wrong_shape = copy.deepcopy(receipt)
            wrong_shape["checkpoint"] = ["not", "a", "mapping"]
            with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_CHECKPOINT_SCOPE"):
                check(helper, wrong_shape)

            # Rehashes can match while an ancestor symlink silently redirects
            # the checkpoint to a different, unpinned storage namespace.
            state.write_text('{"global_step": 1}', encoding="utf-8")
            alias = out / "redirected-output"
            alias.symlink_to(out, target_is_directory=True)
            redirected = copy.deepcopy(receipt)
            redirected["checkpoint"]["path"] = str(alias / "checkpoint-1")
            redirected_check = load_pinned_verifier(alias)["verify_paused_result"]
            with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_CHECKPOINT_SCOPE"):
                redirected_check(helper, redirected)


if __name__ == "__main__":
    unittest.main()
