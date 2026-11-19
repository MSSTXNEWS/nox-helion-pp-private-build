"""B2/4A02: source-isolated regression for optimizer checkpoint step provenance.

Extract the exact functions under test from the pinned owner script without
importing its maintenance entrypoint or starting a service.
"""
import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import types
import unittest
from unittest import mock


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
        "os": os, "stat": stat,
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

            # A concurrent writer can change the JSON after the checkpoint
            # hash sweep. The parsed bytes must still match the signed receipt,
            # even when both old/new documents claim the same global_step.
            original_file_sha = verifier["file_sha"]

            def mutate_state_after_hash(filename):
                observed = original_file_sha(filename)
                if Path(filename) == state:
                    state.write_text('{"global_step":1,"changed_after_hash":true}',
                                     encoding="utf-8")
                return observed

            with mock.patch.dict(verifier, {"file_sha": mutate_state_after_hash}):
                with self.assertRaisesRegex(RuntimeError, "HOLD_PAUSED_CHECKPOINT_HASH"):
                    check(helper, receipt)
            state.write_text('{"global_step": 1}', encoding="utf-8")

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


    def test_bounded_json_state_rejects_descriptor_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read_json = load_pinned_verifier(root)["read_json"]
            safe = root / "safe.json"
            safe.write_text('{"global_step": 1}', encoding="utf-8")
            self.assertEqual(read_json(safe, limit=64), {"global_step": 1})

            # Byte-for-byte matching SHA is insufficient if JSON is ambiguous.
            duplicate = root / "duplicate-step.json"
            duplicate.write_text('{"global_step": 0, "global_step": 1}', encoding="utf-8")
            duplicate_sha = hashlib.sha256(duplicate.read_bytes()).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "HOLD_DUPLICATE_STATE_KEY"):
                read_json(duplicate, limit=128, expected_sha256=duplicate_sha)

            nonfinite = root / "nonfinite-step.json"
            nonfinite.write_text('{"global_step": 1, "loss": NaN}', encoding="utf-8")
            nonfinite_sha = hashlib.sha256(nonfinite.read_bytes()).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "HOLD_NONFINITE_STATE_JSON"):
                read_json(nonfinite, limit=128, expected_sha256=nonfinite_sha)

            oversized = root / "oversized.json"
            oversized.write_text('{"note":"' + "x" * 128 + '"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "HOLD_BOUNDED_STATE_READ"):
                read_json(oversized, limit=64)

            # Simulate a stale preliminary symlink check. Opening the path
            # atomically with O_NOFOLLOW must still reject its redirect.
            alias = root / "redirected.json"
            alias.symlink_to(safe)
            with mock.patch.object(Path, "is_symlink", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "HOLD_BOUNDED_STATE_READ"):
                    read_json(alias, limit=64)

            # A FIFO without a writer must be rejected before a blocking open.
            # Guard the flags in the test itself to bound a regression run.
            fifo = root / "state-fifo"
            os.mkfifo(fifo)
            real_open = os.open

            def checked_open(path, flags, *args, **kwargs):
                if Path(path) == fifo and not flags & os.O_NONBLOCK:
                    raise AssertionError("HOLD_BLOCKING_STATE_DESCRIPTOR_OPEN")
                return real_open(path, flags, *args, **kwargs)

            with mock.patch("os.open", side_effect=checked_open):
                with self.assertRaisesRegex(RuntimeError, "HOLD_BOUNDED_STATE_READ"):
                    read_json(fifo, limit=64)


    def test_checkpoint_file_hash_is_descriptor_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file_sha = load_pinned_verifier(root)["file_sha"]
            safe = root / "adapter_model.safetensors"
            safe.write_bytes(b"checkpoint-bytes")
            self.assertEqual(file_sha(safe), hashlib.sha256(b"checkpoint-bytes").hexdigest())

            # A stale preliminary is_symlink() answer cannot authorize a
            # symlink-swapped checkpoint file at descriptor-open time.
            alias = root / "checkpoint-redirect"
            alias.symlink_to(safe)
            with mock.patch.object(Path, "is_symlink", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "HOLD_SOURCE_PATH"):
                    file_sha(alias)

            # A nonregular filesystem node must not block the SHA reader.
            fifo = root / "checkpoint-fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(RuntimeError, "HOLD_SOURCE_PATH"):
                file_sha(fifo)


    def test_checkpoint_hash_rejects_regular_file_growth_during_read(self):
        # The old EOF-loop silently hashed appended bytes, making an unstable
        # checkpoint appear to be a valid signed snapshot.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "adapter_model.safetensors"
            source.write_bytes(b"initial-weights")
            file_sha = load_pinned_verifier(root)["file_sha"]
            self.assertEqual(file_sha(source), hashlib.sha256(b"initial-weights").hexdigest())
            real_fdopen = os.fdopen

            class AppendOnFirstRead:
                def __init__(self, stream):
                    self.stream = stream
                    self.appended = False

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def fileno(self):
                    return self.stream.fileno()

                def read(self, size):
                    if not self.appended:
                        self.appended = True
                        with source.open("ab") as writer:
                            writer.write(b"-concurrent-append")
                    return self.stream.read(size)

            def concurrent_fdopen(fd, mode):
                return AppendOnFirstRead(real_fdopen(fd, mode))

            with mock.patch("os.fdopen", side_effect=concurrent_fdopen):
                with self.assertRaisesRegex(RuntimeError, "HOLD_CHECKPOINT_FILE_MUTATED"):
                    file_sha(source)



if __name__ == "__main__":
    unittest.main()
