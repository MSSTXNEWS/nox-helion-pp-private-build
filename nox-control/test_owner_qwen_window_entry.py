"""Source-only lifecycle tests; fixture updates are never native model proof."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_qwen_training_contract as c
import owner_qwen_window_entry as w


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def pinned_helper():
    candidates = (Path(__file__).with_name(w.HELPER_NAME),
                  Path(__file__).resolve().parents[2] / "nox-engine-stage/nox-control" / w.HELPER_NAME)
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise unittest.SkipTest("Provide the pinned root installer helper for transport tests")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != w.HELPER_SHA:
        raise AssertionError("Pinned installer helper drift")
    m = types.ModuleType("_test_pinned_qwen_install")
    m.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), m.__dict__)
    return m, raw


def terminal_fixture(goal=5):
    p = {"train_sha256": sha("train"), "holdout_sha256": sha("holdout"),
         "dataset_manifest_sha256": sha("corpus"), "runtime_versions": {"fixture": True},
         "successful_updates_goal": goal}
    lineage = {"schema": c.SCHEMA, "base": {"model_id": c.MODEL_ID, "revision": c.REVISION,
                  "manifest_sha256": c.MANIFEST_SHA, "full_base_sha256_verified": True},
               "target_names": list(c.text_projection_names()), "precision": "NF4_FP16_FP32_LORA",
               **{k: p[k] for k in ("train_sha256", "holdout_sha256", "dataset_manifest_sha256", "runtime_versions")}}
    updates = [{"optimizer_step_before": i, "optimizer_step_after": i + 1,
                "adapter_sha_before": sha("tensor" + str(i)), "adapter_sha_after": sha("tensor" + str(i + 1)),
                "loss": 2.0, "finite_gradients": True, "amp_skipped": False,
                "training_example_sha256": [sha("example" + str(i * 8 + j)) for j in range(8)]}
               for i in range(goal)]
    receipt = {"schema": c.PROOF_SCHEMA, "lineage_sha256": c.canonical_sha(lineage),
               "base_manifest_sha256": c.MANIFEST_SHA, "successful_optimizer_steps": goal,
               "new_successful_optimizer_steps": 5 if goal == 5 else 1,
               "holdout_evaluated_successful_total": goal, "holdout_finite": True,
               "independent_holdout_accepted": True, "old_optimizer_loaded": False,
               "update_evidence": updates, "final_adapter_tensor_sha256": updates[-1]["adapter_sha_after"],
               "reload_verified": goal == 6,
               "state": "STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED" if goal == 5
                        else "STUDENT_RESTART_AND_UPDATES_VERIFIED"}
    return {"profile": p, "contract": c}, lineage, receipt


class ProofTests(unittest.TestCase):
    def test_five_and_reloaded_six_have_different_acceptance(self):
        for goal in (5, 6):
            ctx, lineage, receipt = terminal_fixture(goal)
            w.validate_terminal(ctx, lineage, receipt, goal)
            bad = copy.deepcopy(receipt); bad["reload_verified"] = not receipt["reload_verified"]
            with self.assertRaises(RuntimeError): w.validate_terminal(ctx, lineage, bad, goal)

    def test_counter_only_skipped_or_unchanged_weights_rejected(self):
        ctx, lineage, receipt = terminal_fixture()
        for mutate in (lambda r: r["update_evidence"][2].update(amp_skipped=True),
                       lambda r: r["update_evidence"][2].update(adapter_sha_after=r["update_evidence"][2]["adapter_sha_before"]),
                       lambda r: r.update(independent_holdout_accepted=False),
                       lambda r: r.update(successful_optimizer_steps=20)):
            bad = copy.deepcopy(receipt); mutate(bad)
            with self.assertRaises(RuntimeError): w.validate_terminal(ctx, lineage, bad, 5)

    def test_wrong_base_or_data_lineage_rejected(self):
        ctx, lineage, receipt = terminal_fixture()
        for mutate in (lambda x: x["base"].update(model_id="old/35B"),
                       lambda x: x.update(train_sha256=sha("different snapshot")),
                       lambda x: x.update(target_names=["model.visual.proj"])):
            bad = copy.deepcopy(lineage); mutate(bad)
            with self.assertRaises(RuntimeError): w.validate_terminal(ctx, bad, receipt, 5)


class TransportTests(unittest.TestCase):
    def test_actual_global_materialization_preserves_nested_helper_bundle(self):
        _, raw = pinned_helper()
        bundle = {w.HELPER_NAME: base64.b64encode(raw).decode()}
        source = Path(w.__file__).read_text()
        marker = "__NOX_" + "BUNDLE_JSON__"
        self.assertEqual(source.count(marker), 1)
        namespace = {"__name__": "test_materialized_window", "__file__": w.__file__}
        exec(compile(source.replace(marker, json.dumps(bundle)), w.__file__, "exec"), namespace)
        self.assertEqual(namespace["helper"]().BUNDLE, bundle)

    def test_wrapper_changes_only_goal_and_preserves_initial_bytes(self):
        h, _ = pinned_helper()
        args = ["/root/venv_volta/bin/python", "-u", "/root/nox/scripts/qwen_student_training_entry.py"]
        self.assertEqual(w.wrapper(h, args, "123", 5), h.wrapper(args, "123"))
        for goal in (6, 1000):
            raw = w.wrapper(h, args, "123", goal)
            subprocess.run(["bash", "-n"], input=raw, check=True, capture_output=True)
            latch = raw.decode().split("<<'NOX_QWEN_LATCH'\n", 1)[1].split("NOX_QWEN_LATCH\n", 1)[0]
            compile(latch, "latch", "exec")
            self.assertIn("goal=" + str(goal) + "\\n", latch)
            self.assertIn("O_EXCL", latch)
            self.assertIn('wait "$child_pid"', raw.decode())
        with self.assertRaises(RuntimeError): w.wrapper(h, args, "123", 7)


class HandoffTests(unittest.TestCase):
    def prepare(self, root):
        h, _ = pinned_helper()
        h.ROOT = root; h.STATE = root / "state"; h.SCRIPTS = root / "scripts"
        h.STATE.mkdir(); h.SCRIPTS.mkdir()
        h.ADMISSION = h.STATE / "owner_training_admission.json"
        h.SUPERVISOR = root / "supervisor.conf"
        h.SUPERVISOR.write_text("[program:" + h.SERVICE + "]\nstdout_logfile=NONE\nstderr_logfile=NONE\n")
        h.SUPERVISOR_SHA = c.sha256_file(h.SUPERVISOR)
        h.HOLD = h.STATE / "TRAIN_HOLD.flag"; h.WRAPPER = h.SCRIPTS / "run_train_volta_t866u.sh"
        for n in ("owner_maintenance.lock", "forge_training.lock"):
            (h.STATE / n).write_text("")
        h.ADMISSION.write_bytes(b'{"fixture":true}\n'); h.WRAPPER.write_bytes(b"old fixture wrapper\n")
        owned = w.completion_hold(w.INITIAL_REQUEST, 5); h.HOLD.write_bytes(owned)
        p = {"successful_updates_goal": 5, "base_directory": str(h.STATE / "qwen_memfd"),
             "output_directory": str(root / "lora/qwen35_9b" / w.INITIAL_REQUEST),
             "train_sha256": sha("train"), "holdout_sha256": sha("holdout"),
             "dataset_manifest_sha256": sha("corpus")}
        ctx = {"raw": h.ADMISSION.read_bytes(), "wrapper": h.WRAPPER.read_bytes(),
               "admission": {"request": w.INITIAL_REQUEST}, "profile": p,
               "output": Path(p["output_directory"])}
        evidence = {"hold": owned, "terminal_receipt_sha256": sha("terminal"), "previous_goal": 5, "target_goal": 6}
        h.owner_stop = lambda: False
        h.service = lambda: {"state": "FATAL", "pid": None}
        h.model_identity = lambda: {"pid": 123, "start_ticks": 456}
        h.resource_check = lambda: {"fixture": True}
        return h, ctx, evidence

    def test_unverified_start_latches_owned_failure_and_preserves_completed_hold_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, ctx, evidence = self.prepare(Path(tmp))
            def command(*args, **kwargs):
                raise subprocess.TimeoutExpired("fixture start", 1)
            h.command = command
            with patch.object(w, "context", return_value=ctx), patch.object(w, "validate_advance", return_value=evidence):
                result = w.advance(h, 6, "99901", "a" * 40)
            self.assertEqual(result["state"], "HOLD")
            self.assertEqual(result["failure_hold"], "OWNED_FAILURE_FLAG_CREATED")
            self.assertEqual(h.HOLD.read_text(), "OWNER_QWEN_WINDOW_ADVANCE_FAILED request=99901\n")
            self.assertEqual((h.ROOT / "backup/owner_qwen_window/99901/previous_complete_HOLD.flag").read_bytes(), evidence["hold"])
            self.assertFalse((h.STATE / "OWNER_MAINTENANCE.flag").exists())

    def test_manual_flag_during_start_failure_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, ctx, evidence = self.prepare(Path(tmp))
            def command(*args, **kwargs):
                h.HOLD.write_text("MANUAL OWNER STOP\n")
                raise subprocess.TimeoutExpired("fixture start", 1)
            h.command = command
            with patch.object(w, "context", return_value=ctx), patch.object(w, "validate_advance", return_value=evidence):
                result = w.advance(h, 6, "99902", "a" * 40)
            self.assertEqual(result["failure_hold"], "EXISTING_FLAG_PRESERVED")
            self.assertEqual(h.HOLD.read_text(), "MANUAL OWNER STOP\n")

    def test_active_training_lease_prevents_all_writes_or_start(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            h, ctx, evidence = self.prepare(Path(tmp))
            fd = os.open(h.STATE / "forge_training.lock", os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with patch.object(w, "context") as context:
                    result = w.advance(h, 6, "99903", "a" * 40)
                self.assertEqual(result["state"], "HOLD")
                context.assert_not_called()
                self.assertEqual(h.ADMISSION.read_bytes(), ctx["raw"])
                self.assertEqual(h.HOLD.read_bytes(), evidence["hold"])
                self.assertFalse((h.STATE / "owner_qwen_window_99903.json").exists())
            finally:
                os.close(fd)

    def test_checkpoint_rehash_rejects_changed_optimizer_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, _, _ = self.prepare(Path(tmp))
            ctx, lineage, receipt = terminal_fixture()
            output = Path(tmp) / "output"; output.mkdir(); ctx["output"] = output
            name = "checkpoint-u00000005-a00000005-g00000000000000000001"
            checkpoint = output / name; checkpoint.mkdir()
            names = ("adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "scheduler.pt",
                     "scaler.pt", "rng_state.pt", "python_rng.json")
            for filename in names:
                (checkpoint / filename).write_bytes(b"local fixture only")
            h.atomic(checkpoint / "lineage.json", h.encode(lineage))
            h.atomic(checkpoint / "student_state.json", h.encode({"successful_total": 5,
                     "update_evidence": receipt["update_evidence"]}))
            record = {"schema": "NOX_QWEN35_9B_CHECKPOINT_V1", "directory": name,
                      "lineage_sha256": c.canonical_sha(lineage), "successful_total": 5,
                      "adapter_tensor_sha256": receipt["final_adapter_tensor_sha256"],
                      "files_sha256": {p.name: c.sha256_file(p) for p in checkpoint.iterdir()}}
            h.atomic(checkpoint / "checkpoint_manifest.json", h.encode(record))
            manifest_sha = c.sha256_file(checkpoint / "checkpoint_manifest.json")
            h.atomic(output / "latest_checkpoint.json", h.encode({"directory": name, "manifest_sha256": manifest_sha}))
            receipt.update(checkpoint=str(checkpoint), checkpoint_manifest_sha256=manifest_sha)
            verified = w.verify_checkpoint(h, ctx, receipt, lineage)
            self.assertEqual(verified["verified_files"], 9)
            (checkpoint / "optimizer.pt").write_bytes(b"modified")
            with patch.object(h, "atomic") as atomic:
                with self.assertRaises(RuntimeError): w.verify_checkpoint(h, ctx, receipt, lineage)
                atomic.assert_not_called()

    def test_observe_marks_old_receipt_as_previous_goal_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, ctx, _ = self.prepare(Path(tmp))
            ctx["profile"].update(successful_updates_goal=1000, model_id=c.MODEL_ID, revision=c.REVISION)
            ctx["output"].mkdir(parents=True)
            h.atomic(ctx["output"] / "owner_progress.json", h.encode({"successful_optimizer_steps": 10}))
            h.atomic(ctx["output"] / "owner_last_result.json", h.encode({"successful_optimizer_steps": 6,
                     "reload_verified": True, "independent_holdout_accepted": True}))
            with patch.object(w, "context", return_value=ctx), patch.object(h, "atomic") as atomic:
                observed = w.observe(h)
                atomic.assert_not_called()
            self.assertFalse(observed["final_result"]["matches_current_goal"])
            self.assertEqual(observed["progress"]["successful_optimizer_steps"], 10)
            self.assertEqual(observed["files_written"], 0)

    def test_user_replacement_between_check_and_rename_is_preserved_and_not_accepted(self):
        for symlink in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                h, _, evidence = self.prepare(Path(tmp))
                saved = h.ROOT / "saved_hold"
                real_rename = w.rename_noreplace
                def race(source, destination):
                    replacement = h.ROOT / "replacement"
                    if symlink:
                        replacement.symlink_to(h.ROOT / "owner_target")
                    else:
                        replacement.write_text("MANUAL OWNER STOP\n")
                    os.replace(replacement, h.HOLD)
                    real_rename(source, destination)
                with patch.object(w, "rename_noreplace", side_effect=race):
                    result = w.archive_completed_hold(h, saved, evidence["hold"])
                self.assertFalse(result["expected_flag"])
                self.assertTrue(os.path.lexists(saved))
                if symlink:
                    self.assertTrue(h.HOLD.is_symlink())
                    self.assertEqual(os.readlink(h.HOLD), str(h.ROOT / "owner_target"))
                else:
                    self.assertEqual(h.HOLD.read_text(), "MANUAL OWNER STOP\n")

    def test_fresh_manual_flag_during_rollback_link_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, _, evidence = self.prepare(Path(tmp))
            saved = h.ROOT / "saved_hold"
            saved.write_bytes(evidence["hold"]); h.HOLD.unlink()
            real_link = os.link
            def race(source, destination, **kwargs):
                h.HOLD.write_text("FRESH MANUAL STOP\n")
                return real_link(source, destination, **kwargs)
            with patch.object(w.os, "link", side_effect=race):
                result = w.restore_hold_noclobber(h, saved)
            self.assertEqual(result, "NEW_FLAG_PRESERVED_SAVED_FLAG_RETAINED")
            self.assertEqual(h.HOLD.read_text(), "FRESH MANUAL STOP\n")
            self.assertEqual(saved.read_bytes(), evidence["hold"])

    def test_log_diagnostic_never_returns_message_input_url_or_filename(self):
        raw = (b'ValueError: PRIVATE_CORPUS token=SECRET https://secret.example/path\n'
               b'Hold: HOLD_QWEN_PUBLIC_PROBE\n'
               b'{"state":{"private":"SECRET"}}\n'
               b'{"state":"PINNED_PUBLIC_BASE_STAGING","file":"SECRET_FILE","bytes":1024,"total":2048}\n')
        result = w.safe_log_summary(raw)
        text = json.dumps(result)
        for secret in ("PRIVATE", "SECRET", "https://", "example/path"):
            self.assertNotIn(secret, text)
        self.assertEqual(result["exception_types"], ["ValueError", "Hold"])
        self.assertEqual(result["hold_codes"], ["HOLD_QWEN_PUBLIC_PROBE"])


if __name__ == "__main__":
    unittest.main()
