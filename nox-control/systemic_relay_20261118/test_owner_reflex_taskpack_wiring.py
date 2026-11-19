"""Dispatcher wiring tests for the inert Reflex successor taskpack."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(1, str(HERE.parent / "complete_executor_20261118/runtime"))
sys.path.insert(0, str(HERE.parent))

import owner_native_operator as operator
import owner_subagent_dispatcher as dispatcher
import owner_systemic_refill as refill
import owner_reflex_taskpack as taskpack

MANIFEST_PATH = (HERE / "next_pack_44368502183/package/relay/"
                 "d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212.json")
MANIFEST_SHA = "d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212"
PIN = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def import_entry():
    path = HERE / "owner_native_reflex_successor_entry.py"
    spec = importlib.util.spec_from_file_location("reflex_successor_entry_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReflexTaskpackWiringTests(unittest.TestCase):
    def test_owner_gate_prevents_proposal_builder_from_running_without_authority(self):
        native = dispatcher.Native.__new__(dispatcher.Native)
        native.projects = object()
        native.owner_allowed = lambda: False
        native.stop_active = lambda: False
        native.writer_lease = lambda: True
        native._relay_modules = lambda: self.fail("module load crossed owner gate")
        with self.assertRaisesRegex(dispatcher.GateError, "HOLD_RELAY_OWNER_GATE"):
            native._refill_under_lease({"path": "/unused", "sha256": MANIFEST_SHA},
                                       {"tasks": []})

    def test_actual_dispatcher_refill_keeps_successor_proposal_out_of_queue(self):
        manifest = json.loads(MANIFEST_PATH.read_text())
        original_manifest = json.loads(json.dumps(manifest))
        source_pins = {"NOX_PROJECT_SOURCE": {}}
        for mission in manifest["missions"]:
            for row in mission["context"]:
                source_pins[mission["root_id"]][row["path"]] = row["sha256"]
            editable = mission["editable_paths"][0]
            source_pins[mission["root_id"]][editable] = "b" * 64

        native = dispatcher.Native.__new__(dispatcher.Native)
        native.ns = {"_qlock": threading.RLock()}
        native.config = {"module_pins": {
            "owner_systemic_refill.py": PIN(RUNTIME / "owner_systemic_refill.py"),
            "owner_reflex_taskpack.py": PIN(RUNTIME / "owner_reflex_taskpack.py"),
        }}
        native.source = "c" * 64
        native.state = {"tasks": {}}
        native.catalog = {"tasks": []}
        native.relay_status = {"state": "NOT_CONFIGURED"}
        native._relay_bindings = {}
        native._relay_current_sha256 = None
        native._relay_manifest_cache = {}
        native.projects = type("Projects", (), {
            "config": {"package_root": tempfile.gettempdir()},
            "terminal_for_capacity": staticmethod(lambda _task: False),
        })()
        native.owner_allowed = lambda: True
        native.stop_active = lambda: False
        native.writer_lease = lambda: True
        native.allowed_handlers = lambda: {
            dispatcher.HANDLER, dispatcher.LEAF_HANDLER, dispatcher.PROJECT_HANDLER}
        native.read_resource_snapshot = lambda leaf_only=True: {}
        native._validate_catalog = lambda catalog: catalog["tasks"]
        native._relay_manifests = lambda _reference, _module: {MANIFEST_SHA: manifest}
        native._relay_source_pins = lambda _module, _manifest: source_pins

        reference = {"path": "/unused/" + MANIFEST_SHA + ".json",
                     "sha256": MANIFEST_SHA}
        base = {"tasks": []}
        with patch.object(dispatcher, "resource_wait_reason", return_value=None):
            result = native._refill_under_lease(reference, base)

        self.assertEqual(result["tasks"], [])
        self.assertEqual(native.relay_status["eligible_proposals"], 0)
        self.assertEqual(native.relay_status["original_task_acceptance_added"], 0)
        self.assertEqual(manifest, original_manifest)
        proposal = native.relay_status["successor_proposal"]
        self.assertEqual(proposal["schema"], "NOX_NATIVE_REFLEX_DRAFT_TASKPACK_V1")
        self.assertEqual(proposal["authority"], "PROPOSAL_ONLY")
        self.assertFalse(proposal["automatic_owner_approval"])
        self.assertEqual(proposal["native_jobs_created"], 0)
        self.assertLessEqual(len(proposal["decisions"]), taskpack.MAX_OBSERVED)
        self.assertLessEqual(len(proposal["draft_missions"]), taskpack.MAX)
        self.assertEqual(len(proposal["draft_missions"]), 3)
        self.assertEqual(proposal["draft_manifest"]["review_origin"],
                         "UNREVIEWED_REFLEX_DRAFT")
        self.assertEqual(proposal["draft_manifest"]["acceptance_scope"], "DRAFT_ONLY")
        self.assertFalse(proposal["draft_manifest"]["original_task_accepted"])
        self.assertEqual(native.relay_status["self_monitor"]["staged_count"], 3)

    def test_owner_bundle_pins_taskpack_with_only_four_runtime_assets(self):
        entry = import_entry()
        self.assertEqual(entry.OLD, {
            entry.CONFIG: "da355cfbd8bb07d543d388e6de19cfb05850c1ca7f5f28d75936507d540917b9",
            entry.REFILL: "06bb8ec21607f09a5703e3f1b7d8694bbc120485e80c14058128902c6d9959ba",
            entry.DIRECTOR: "eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11",
        })
        bundle = {
            "owner_systemic_refill.py": (RUNTIME / "owner_systemic_refill.py").read_bytes(),
            "owner_subagent_dispatcher.py": (RUNTIME / "owner_subagent_dispatcher.py").read_bytes(),
            "owner_reflex_taskpack.py": (RUNTIME / "owner_reflex_taskpack.py").read_bytes(),
            "continuous_transaction_helpers.py": (
                HERE.parent / "continuous_executor_20261118/assets/"
                "continuous_transaction_helpers.py").read_bytes(),
        }
        entry.BUNDLE = {name: base64.b64encode(raw).decode("ascii")
                        for name, raw in bundle.items()}
        helper, scripts = entry.decode()
        self.assertTrue(callable(helper.preimages))
        self.assertEqual(scripts[entry.TASKPACK], bundle["owner_reflex_taskpack.py"])
        self.assertIn("owner_reflex_taskpack.py", entry.TASKPACK)
        self.assertIn("owner_reflex_taskpack.py", entry.__dict__["TASKPACK"])
        old_config = {"module_pins": {"previous": "d" * 64}}
        pinned = entry.pin_successor_modules(old_config, scripts)
        self.assertEqual(pinned["module_pins"]["owner_reflex_taskpack.py"],
                         hashlib.sha256(bundle["owner_reflex_taskpack.py"]).hexdigest())
        self.assertEqual(pinned["module_pins"]["owner_systemic_refill.py"],
                         hashlib.sha256(bundle["owner_systemic_refill.py"]).hexdigest())
        self.assertNotIn("owner_reflex_taskpack.py", old_config["module_pins"])
        self.assertEqual(set(operator.repair_bundle_paths(
            "reflex_successor", operator.FILES["reflex_successor"], ())),
            {"nox-control/systemic_relay_20261118/runtime/owner_systemic_refill.py",
             "nox-control/systemic_relay_20261118/runtime/owner_subagent_dispatcher.py",
             "nox-control/systemic_relay_20261118/runtime/owner_reflex_taskpack.py",
             "nox-control/continuous_executor_20261118/assets/"
             "continuous_transaction_helpers.py"})
        self.assertEqual(operator.FILES["reflex_successor"],
                         "nox-control/systemic_relay_20261118/owner_native_reflex_successor_entry.py")

    def test_owner_action_accepts_only_its_bounded_successor_receipt(self):
        draft = {"schema": "NOX_NATIVE_REFLEX_DRAFT_MANIFEST_V1",
                 "review_origin": "UNREVIEWED_REFLEX_DRAFT",
                 "acceptance_scope": "DRAFT_ONLY",
                 "original_task_accepted": False,
                 "missions": []}
        draft_sha = hashlib.sha256(json.dumps(
            draft, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        receipt = {"schema": "NOX_NATIVE_REFLEX_UPGRADE_RECEIPT_V1",
                   "state": "NATIVE_REFLEX_TELEMETRY_VERIFIED",
                   "source_sha": "a" * 40, "request": "411",
                   "runtime_files_changed": 3, "new_native_jobs": 0,
                   "base_manifest_sha256": MANIFEST_SHA,
                   "monitor_observation_sha256": "b" * 64,
                   "draft_manifest_sha256": draft_sha,
                   "successor_proposal_sha256": draft_sha,
                   "successor_authority": "PROPOSAL_ONLY",
                   "successor_decisions": [{"state": "DRAFT_REQUIRES_OWNER_REVIEW"}],
                   "successor_draft_missions": [{"id": "draft-1"}],
                   "successor_draft_manifest": draft,
                   "successor_required_next_step":
                       "INDEPENDENT_REVIEW_AND_OWNER_PINNED_MANIFEST_CAS"}
        operator._validate_forward_marker(
            "reflex_successor", "NOX_MAINT_REFLEX_SUCCESSOR=" + json.dumps(receipt))
        operator._validate_forward_marker(
            "reflex_successor", "NOX_MAINT_REFLEX_SUCCESSOR_COMPLETE=true")
        hold = {"schema": "NOX_NATIVE_REFLEX_UPGRADE_RECEIPT_V1",
                "source_sha": "a" * 40, "request": "411",
                "state": "HOLD_NATIVE_REFLEX_WRITE_POSTIMAGE",
                "rollback_verified": False}
        operator._validate_forward_marker(
            "reflex_successor", "NOX_MAINT_REFLEX_SUCCESSOR_HOLD=" + json.dumps(hold))
        with self.assertRaisesRegex(RuntimeError, "HOLD_REMOTE_MARKER_NOT_ALLOWLISTED"):
            operator._validate_forward_marker("reflex_successor", "NOX_MAINT_REPAIR_COMPLETE=true")

    def test_taskpack_atomic_failure_before_and_after_replace_rolls_back_exactly(self):
        entry = import_entry()
        bundle = {
            "owner_systemic_refill.py": (RUNTIME / "owner_systemic_refill.py").read_bytes(),
            "owner_subagent_dispatcher.py": (RUNTIME / "owner_subagent_dispatcher.py").read_bytes(),
            "owner_reflex_taskpack.py": (RUNTIME / "owner_reflex_taskpack.py").read_bytes(),
            "continuous_transaction_helpers.py": (
                HERE.parent / "continuous_executor_20261118/assets/"
                "continuous_transaction_helpers.py").read_bytes(),
        }
        entry.BUNDLE = {name: base64.b64encode(raw).decode("ascii")
                        for name, raw in bundle.items()}
        helper, _ = entry.decode()

        for fail_after_replace in (False, True):
            with self.subTest(fail_after_replace=fail_after_replace), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                before = {
                    entry.REFILL: b"old refill",
                    entry.DIRECTOR: b"old director",
                    entry.TASKPACK: None,
                    entry.CONFIG: b"old config",
                }
                for relative, raw in before.items():
                    if raw is not None:
                        path = root / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                changes = {relative: (b"new " + relative.encode())
                           for relative in before}
                applied = []
                injected = False

                def atomic(path, raw, mode=0o600):
                    nonlocal injected
                    if path == root / entry.TASKPACK and not injected:
                        injected = True
                        if fail_after_replace:
                            helper.atomic(path, raw, mode)
                        raise OSError("injected TASKPACK atomic failure")
                    return helper.atomic(path, raw, mode)

                failing_helper = SimpleNamespace(read_regular=helper.read_regular,
                                                 atomic=atomic)
                with self.assertRaisesRegex(OSError, "injected TASKPACK"):
                    entry.apply_source_changes(failing_helper, root, changes,
                                               before, applied)
                self.assertEqual(applied, [entry.REFILL, entry.DIRECTOR, entry.TASKPACK])
                self.assertTrue(entry.rollback_source_changes(
                    helper, root, changes, before, applied))
                for relative, expected in before.items():
                    path = root / relative
                    if expected is None:
                        self.assertFalse(path.exists())
                    else:
                        self.assertEqual(path.read_bytes(), expected)

    def test_failed_start_after_full_write_restores_before_restart(self):
        entry = import_entry()
        bundle = {
            "owner_systemic_refill.py": (RUNTIME / "owner_systemic_refill.py").read_bytes(),
            "owner_subagent_dispatcher.py": (RUNTIME / "owner_subagent_dispatcher.py").read_bytes(),
            "owner_reflex_taskpack.py": (RUNTIME / "owner_reflex_taskpack.py").read_bytes(),
            "continuous_transaction_helpers.py": (
                HERE.parent / "continuous_executor_20261118/assets/"
                "continuous_transaction_helpers.py").read_bytes(),
        }
        entry.BUNDLE = {name: base64.b64encode(raw).decode("ascii")
                        for name, raw in bundle.items()}
        helper, _ = entry.decode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = {entry.REFILL: b"old refill", entry.DIRECTOR: b"old director",
                      entry.TASKPACK: None, entry.CONFIG: b"old config"}
            for relative, raw in before.items():
                if raw is not None:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            changes = {relative: b"new " + relative.encode() for relative in before}
            applied = []
            entry.apply_source_changes(helper, root, changes, before, applied)
            self.assertEqual(applied, list(changes))
            # The simulated supervisor start fails after all new sources landed.
            with self.assertRaisesRegex(RuntimeError, "injected start failure"):
                raise RuntimeError("injected start failure")
            verified = entry.rollback_source_changes(helper, root, changes, before, applied)
            self.assertTrue(verified)
            self.assertTrue(entry.may_restart_after_rollback(True, "STOPPED", verified))
            for relative, expected in before.items():
                path = root / relative
                if expected is None:
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(path.read_bytes(), expected)

    def test_failed_rollback_never_authorizes_prior_director_restart(self):
        entry = import_entry()
        bundle = {
            "owner_systemic_refill.py": (RUNTIME / "owner_systemic_refill.py").read_bytes(),
            "owner_subagent_dispatcher.py": (RUNTIME / "owner_subagent_dispatcher.py").read_bytes(),
            "owner_reflex_taskpack.py": (RUNTIME / "owner_reflex_taskpack.py").read_bytes(),
            "continuous_transaction_helpers.py": (
                HERE.parent / "continuous_executor_20261118/assets/"
                "continuous_transaction_helpers.py").read_bytes(),
        }
        entry.BUNDLE = {name: base64.b64encode(raw).decode("ascii")
                        for name, raw in bundle.items()}
        helper, _ = entry.decode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = {entry.REFILL: b"old refill", entry.DIRECTOR: b"old director",
                      entry.TASKPACK: None, entry.CONFIG: b"old config"}
            for relative, raw in before.items():
                if raw is not None:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            changes = {relative: b"new " + relative.encode() for relative in before}
            applied = []
            entry.apply_source_changes(helper, root, changes, before, applied)

            def fail_rollback(_path, _raw, _mode=0o600):
                raise OSError("injected rollback failure")

            failing_helper = SimpleNamespace(read_regular=helper.read_regular,
                                             atomic=fail_rollback)
            verified = entry.rollback_source_changes(
                failing_helper, root, changes, before, applied)
            self.assertFalse(verified)
            self.assertFalse(entry.may_restart_after_rollback(True, "STOPPED", verified))
            self.assertFalse(entry.may_restart_after_rollback(True, "STOPPED", False))
            self.assertFalse(entry.may_restart_after_rollback(True, "RUNNING", True))


if __name__ == "__main__":
    unittest.main()
