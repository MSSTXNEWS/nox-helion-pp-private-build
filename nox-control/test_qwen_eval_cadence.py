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
        fn, cls.tree = isolated_decision()
        cls.due = staticmethod(fn)

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


class CheckpointRetentionNoLossTest(unittest.TestCase):
    """Actual prune_checkpoints source, isolated without CUDA/PEFT imports."""

    def _fixture(self, root):
        import hashlib
        import json
        import re

        lineage = {"model": "Qwen3.5-9B", "revision": "pinned"}
        digest = lambda value: hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        run_dir = root / "lora" / "qwen35_9b" / "test_run"
        run_dir.mkdir(parents=True)
        entries = []
        for i in range(1, 6):
            name = f"checkpoint-u{i:08d}-a{i:08d}-g{i:020d}"
            folder = run_dir / name
            folder.mkdir()
            (folder / "optimizer.pt").write_bytes(b"unique optimizer data " + bytes([i]))
            entries.append({"directory": name, "manifest_sha256": f"{i:064x}",
                            "successful_total": i, "attempted_total": i,
                            "evaluated_at_current_step": i == 2,
                            "holdout_loss": 1.0 if i == 2 else 2.0,
                            "retained": True})
        ledger = {"schema": "NOX_QWEN_OWNED_CHECKPOINTS_V1",
                  "lineage_sha256": digest(lineage), "checkpoints": entries}
        (run_dir / "owner_checkpoints.json").write_text(json.dumps(ledger))
        (run_dir / "latest_checkpoint.json").write_text(json.dumps(
            {"directory": entries[-1]["directory"],
             "manifest_sha256": entries[-1]["manifest_sha256"]}))
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "prune_checkpoints"]
        self.assertEqual(len(nodes), 1)
        namespace = {
            "Path": Path, "ROOT": root, "Hold": Hold,
            "CHECKPOINT_NAME": re.compile(r"checkpoint-u\d{8}-a\d{8}-g\d{20}"),
            "math": math, "canonical_sha": digest,
            "check_path": lambda path: Path(path),
            "read_json": lambda path: json.loads(Path(path).read_text()),
            "verify_proof": lambda *_args, **_kwargs: None
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
        return namespace["prune_checkpoints"], run_dir, lineage, entries, nodes[0]

    def test_old_optimizer_files_not_auto_deleted_without_restore(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            prune, run_dir, lineage, entries, _ = self._fixture(root)
            result = prune(run_dir, lineage)
            self.assertEqual(result["deleted_verified_own_checkpoints"], 0)
            self.assertEqual(result["cleanup_hold"],
                             "HOLD_INDEPENDENT_RESTORE_AND_SINGLE_CLEANUP_WRITER")
            self.assertEqual(result["pending_external_cleanup"],
                             [entries[0]["directory"], entries[2]["directory"]])
            for row in entries:
                self.assertTrue((run_dir / row["directory"] / "optimizer.pt").is_file())
            self.assertTrue(all(row["retained"] for row in
                                __import__("json").loads(
                                    (run_dir / "owner_checkpoints.json").read_text())["checkpoints"]))

    def test_owner_acceptance_is_not_offsite_recovery_evidence(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            prune, run_dir, lineage, entries, _ = self._fixture(Path(t))
            (run_dir / "owner_acceptance.json").write_text(
                json.dumps({"checkpoint": str(run_dir / entries[0]["directory"])}))
            result = prune(run_dir, lineage)
            self.assertEqual(result["deleted_verified_own_checkpoints"], 0)
            self.assertIn(entries[2]["directory"], result["pending_external_cleanup"])
            self.assertTrue((run_dir / entries[2]["directory"] / "optimizer.pt").exists())

    def test_unknown_latest_pointer_fails_closed(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            prune, run_dir, lineage, _, _ = self._fixture(Path(t))
            (run_dir / "latest_checkpoint.json").write_text(
                json.dumps({"directory": "checkpoint-u00000088-a00000088-g00000000000000000088",
                            "manifest_sha256": "0" * 64}))
            with self.assertRaises(Hold):
                prune(run_dir, lineage)

    def test_prune_source_has_no_file_delete_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            _, _, _, _, node = self._fixture(Path(t))
            methods = {x.func.attr for x in ast.walk(node)
                       if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)}
            self.assertFalse(methods & {"unlink", "rmdir", "rmtree", "remove"})


class CheckpointPublicationOrderingTest(unittest.TestCase):
    """Exercise the real save_checkpoint function with file-only fake dependencies."""

    def _exercise(self, *, fail_ledger=False, invalid_ledger=False):
        import hashlib
        import json
        import os
        import random
        import tempfile
        import time
        import types

        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "save_checkpoint"]
        self.assertEqual(len(fn), 1)

        class Model:
            def save_pretrained(self, path, **_kwargs):
                (path / "adapter_model.safetensors").write_bytes(b"unique-new-adapter")
                (path / "adapter_config.json").write_text("{}")

        class Torch:
            cuda = types.SimpleNamespace(get_rng_state_all=lambda: [b"cuda"])
            get_rng_state = staticmethod(lambda: b"cpu")
            save = staticmethod(lambda value, path: Path(path).write_bytes(repr(value).encode()))

        digest = lambda value: hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        sha_file = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        lineage = {"base": "exact-qwen-pinned-test"}
        old_pointer = {"directory": "checkpoint-u00000001-a00000001-g00000000000000000001",
                       "manifest_sha256": "a" * 64}
        previous_ledger = {"schema": "NOX_QWEN_OWNED_CHECKPOINTS_V1",
                           "lineage_sha256": digest(lineage), "checkpoints": []}
        if invalid_ledger:
            previous_ledger["lineage_sha256"] = "b" * 64

        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            pointer_path = output / "latest_checkpoint.json"
            ledger_path = output / "owner_checkpoints.json"
            pointer_path.write_text(json.dumps(old_pointer))
            ledger_path.write_text(json.dumps(previous_ledger))
            calls = []

            def write(path, value, **_kwargs):
                path = Path(path)
                calls.append(path.name)
                if fail_ledger and path == ledger_path:
                    raise OSError("injected ledger disk-write failure")
                path.write_text(json.dumps(value, sort_keys=True, allow_nan=False))

            def read(path):
                return json.loads(Path(path).read_text())

            namespace = {"Path": Path, "GIB": 1024 ** 3, "Hold": Hold,
                         "ROOT": output, "tempfile": tempfile, "time": time,
                         "os": os, "random": random, "torch": Torch,
                         "check_resources": lambda *_args, **_kwargs: None,
                         "read_json": read, "atomic_json": write,
                         "canonical_sha": digest, "sha256_file": sha_file,
                         "adapter_hash": lambda *_: "c" * 64,
                         "process_identity": lambda: {"pid": 1},
                         "prune_checkpoints": lambda *_: calls.append("prune")}
            exec(compile(ast.Module(body=fn, type_ignores=[]),
                         str(SOURCE), "exec"), namespace)
            fake = types.SimpleNamespace(state_dict=lambda: {"ok": True})
            invoke = lambda: namespace["save_checkpoint"](
                output, Model(), fake, fake, fake,
                {"successful_total": 2, "attempted_total": 2,
                 "holdout_evaluated_successful_total": 2,
                 "last_holdout_loss": 1.2},
                lineage, Torch)

            if invalid_ledger:
                with self.assertRaises(Hold):
                    invoke()
                self.assertFalse(any(p.name.startswith("checkpoint-u") for p in output.iterdir()))
                self.assertNotIn("owner_checkpoints.json", calls)
            elif fail_ledger:
                with self.assertRaises(OSError):
                    invoke()
                # No orphan is silently deleted; latest still points to the prior
                # acknowledged version, and the original ledger is unchanged.
                self.assertTrue(any(p.name.startswith("checkpoint-u") for p in output.iterdir()))
                self.assertIn("owner_checkpoints.json", calls)
                self.assertNotIn("latest_checkpoint.json", calls)
            else:
                folder, record = invoke()
                self.assertTrue((folder / "optimizer.pt").is_file())
                pointer = read(pointer_path)
                ledger = read(ledger_path)
                self.assertEqual(pointer["directory"], folder.name)
                self.assertEqual(ledger["checkpoints"][-1]["directory"], folder.name)
                self.assertEqual(pointer["manifest_sha256"], sha_file(folder / "checkpoint_manifest.json"))
                self.assertLess(calls.index("owner_checkpoints.json"),
                                calls.index("latest_checkpoint.json"))
                self.assertEqual(calls[-1], "prune")
            if fail_ledger or invalid_ledger:
                self.assertEqual(read(pointer_path), old_pointer)
                self.assertEqual(read(ledger_path), previous_ledger)

    def test_successful_checkpoint_publishes_owner_ledger_first(self):
        self._exercise()

    def test_failed_ledger_write_does_not_advance_latest_pointer(self):
        self._exercise(fail_ledger=True)

    def test_invalid_ledger_fails_before_large_checkpoint_write(self):
        self._exercise(invalid_ledger=True)


if __name__ == "__main__":
    unittest.main()
