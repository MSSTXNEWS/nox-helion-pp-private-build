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
import shlex
import stat
import tempfile
import types
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "owner_training_resume.py"
FN_NAMES = {"read_json", "file_sha", "verify_paused_result", "resource_admission",
            "continuation_terminal_state", "read_installed_train_cpu_cap",
            "owned_flag", "stop_controller"}


def load_pinned_verifier(output):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in FN_NAMES]
    if {node.name for node in nodes} != FN_NAMES:
        raise AssertionError("HOLD_EXACT_OWNER_VERIFIER_MISSING")
    namespace = {
        "Path": Path, "hashlib": hashlib, "json": json, "math": math,
        "os": os, "shlex": shlex, "stat": stat,
        "re": re, "OUTPUT": output, "STATE": output,
        "STOPPED": ("STOPPED", "EXITED", "FATAL"),
        "global_stop": lambda: False, "lease_free": lambda: True,
        "native_training": lambda helper: False,
        "NATIVE_SHA": "a" * 64,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace


class CheckpointStepProvenance(unittest.TestCase):

    def test_boost_policy_native_root_snapshot_fail_closed(self):
        # Execute actual pinned verifier AST; never import or launch trainer.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        node = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "verify_policy"), None)
        self.assertIsNotNone(node)
        namespace = {"BOOST_REQUEST": "pinned-request",
                     "BOOST_SOURCE": "a" * 40}
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        verify = namespace["verify_policy"]
        valid = {"enabled": True, "mode": "TASK_BOOST",
                 "request": "pinned-request", "source_sha": "a" * 40}
        self.assertIsNone(verify(valid))
        for malformed in (None, [], "offline", True, 1, {}, {"enabled": 1},
                          {"enabled": False, "mode": "TASK_BOOST"}):
            with self.subTest(snapshot=repr(malformed)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_NATIVE_BOOST_POLICY_CHANGED$"):
                    verify(malformed)

    def test_native_training_process_census_fail_closed_before_admission(self):
        # Execute the actual source AST only; no process, trainer or GPU access.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "native_training")
        namespace = {
            "TRAINER": Path("/root/nox/scripts/train_qlora_35b_t866u.py"),
            "ENTRY": Path("/root/nox/scripts/hybrid_training_entry.py"),
            "WRAPPER": Path("/root/nox/scripts/run_train_volta_t866u.sh"),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        census = namespace["native_training"]
        malformed = (
            None, [], "not-a-map", {"w": None}, {"w": []},
            {"w": {}}, {"w": {"state": None}},
            {"w": {"state": True, "argv": []}},
            {"w": {"state": "R"}},
            {"w": {"state": "R", "argv": "python"}},
            {"w": {"state": "R", "argv": [None]}},
            {"w": {"state": "R", "argv": [True]}},
            {"w": {"state": "R", "argv": {"argv": "hidden"}}},
        )
        for snapshot in malformed:
            with self.subTest(snapshot=repr(snapshot)):
                helper = types.SimpleNamespace(
                    process_table=lambda value=snapshot: value)
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_NATIVE_TRAINER_CENSUS_READBACK"):
                    census(helper)
        entry = str(namespace["ENTRY"])
        trainer = {"state": "R", "argv": ["python", entry], "service": "nox-train-volta-t866u"}
        healthy = {"zombie": {"state": "Z"},
                   "unrelated": {"state": "R", "argv": ["python", "else.py"]},
                   "trainer": trainer}
        self.assertEqual(
            census(types.SimpleNamespace(process_table=lambda: healthy)),
            [trainer])
        self.assertEqual(
            census(types.SimpleNamespace(process_table=lambda: {})), [])

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

            # JSON receipts may decode to a scalar, array or null. The
            # optimizer proof must return a named durable HOLD, never crash
            # before recording the root evidence fault.
            for malformed_root in (None, [], ["spoof"], "checkpoint", False,
                                   0, 1.5):
                with self.subTest(receipt_root=repr(malformed_root)):
                    with self.assertRaisesRegex(
                            RuntimeError, "^HOLD_PAUSED_OPTIMIZER_RECEIPT$"):
                        check(helper, malformed_root)

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


    def test_signed_checkpoint_json_huge_integer_is_named_hold(self):
        # Python 3.11+ may raise ValueError during json.loads when a signed
        # decimal integer exceeds sys.get_int_max_str_digits() (default 4300).
        # Exercise the *actual* read_json function, not an imitation.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "trainer_state.json"
            read_json = load_pinned_verifier(Path(folder))["read_json"]
            huge = b'{"global_step":' + b'9' * 5000 + b'}'
            source.write_bytes(huge)
            signed_hash = hashlib.sha256(huge).hexdigest()
            with self.assertRaisesRegex(
                    RuntimeError, "^HOLD_INVALID_STATE_JSON$"):
                read_json(source, expected_sha256=signed_hash)
            valid = b'{"global_step":2}'
            source.write_bytes(valid)
            self.assertEqual(
                read_json(source, expected_sha256=hashlib.sha256(valid).hexdigest()),
                {"global_step": 2})

    def test_signed_checkpoint_json_extreme_depth_is_named_hold(self):
        # A SHA-256-matching JSON file can still exceed json.loads nesting
        # limits while remaining far under the bounded descriptor byte limit.
        # Exercise the actual source function; no training process or S03 write.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "trainer_state.json"
            read_json = load_pinned_verifier(Path(folder))["read_json"]
            deeply_nested = (b'{"events":' + b'[' * 10000
                             + b'0' + b']' * 10000 + b'}')
            source.write_bytes(deeply_nested)
            with self.assertRaisesRegex(
                    RuntimeError, "^HOLD_INVALID_STATE_JSON$"):
                read_json(source, expected_sha256=hashlib.sha256(
                    deeply_nested).hexdigest())
            healthy = b'{"global_step":2,"events":[1,2,3]}'
            source.write_bytes(healthy)
            self.assertEqual(
                read_json(source, expected_sha256=hashlib.sha256(
                    healthy).hexdigest()),
                {"global_step": 2, "events": [1, 2, 3]})

    def test_negative_cross_entropy_loss_denied_even_with_valid_checkpoint_hashes(self):
        # Signed SHA bytes and a positive optimizer step cannot legitimate a
        # finite negative cross-entropy loss. No service or trainer is run.
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            cp = out / "checkpoint-1"
            cp.mkdir()
            (cp / "adapter_model.safetensors").write_bytes(b"verified-test-adapter")
            (cp / "trainer_state.json").write_text(
                '{"global_step":1}', encoding="utf-8")
            verifier = load_pinned_verifier(out)
            names = ("adapter_model.safetensors", "trainer_state.json")
            hashes = {name: verifier["file_sha"](cp / name) for name in names}
            receipt = {
                "global_step": 1, "state": "CHECKPOINTED_OWNER_STOP",
                "native_sha256": "a" * 64, "successful_optimizer_steps": 1,
                "adapter_delta_verified": True,
                "before_tensor_sha256": "b" * 64,
                "after_tensor_sha256": "c" * 64,
                "checkpoint": {
                    "path": str(cp), "global_step": 1,
                    "files_sha256": hashes,
                },
                "loss": 0.5,
            }
            check = verifier["verify_paused_result"]
            helper = types.SimpleNamespace(CHECKPOINT_NAMES=names)
            self.assertTrue(check(helper, receipt))
            self.assertTrue(check(helper, {**receipt, "loss": 0.0}))
            self.assertTrue(check(helper, {**receipt, "loss": 7}))
            # Signed JSON with a 400-digit integer loss used to escape as
            # OverflowError from math.isfinite(), not a stable owner HOLD.
            for invalid_loss in (-0.25, -1, -1e-300, 10**400, -(10**400),
                                 float('inf'), float('-inf'), float('nan'),
                                 True, '0.5'):
                with self.subTest(loss=invalid_loss):
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_PAUSED_OPTIMIZER_RECEIPT"):
                        check(helper, {**receipt, "loss": invalid_loss})


    def test_stop_controller_state_shape_and_pid_guard_before_supervisor_stop(self):
        # Isolated AST function: no real Supervisor command, worker, or STOP.
        stop = load_pinned_verifier(Path("/tmp"))["stop_controller"]
        script = Path("/root/nox/scripts/nox_dispatcher_t855u.py")
        name = "nox-dispatcher-t855u"
        malformed = (
            (None, "HOLD_EXPECTED_CONTROLLER_NOT_RUNNING"),
            ([], "HOLD_EXPECTED_CONTROLLER_NOT_RUNNING"),
            ({}, "HOLD_EXPECTED_CONTROLLER_NOT_RUNNING"),
            ({"state": "STOPPED"}, "HOLD_EXPECTED_CONTROLLER_NOT_RUNNING"),
            ({"state": True}, "HOLD_EXPECTED_CONTROLLER_NOT_RUNNING"),
            ({"state": "RUNNING"}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": None}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": True}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": False}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": 0}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": -3}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": "321"}, "HOLD_CONTROLLER_IDENTITY"),
            ({"state": "RUNNING", "pid": [321]}, "HOLD_CONTROLLER_IDENTITY"),
        )
        for snapshot, reason in malformed:
            with self.subTest(snapshot=snapshot):
                helper = types.SimpleNamespace(
                    service_state=lambda _name, value=snapshot: value,
                    program_config=lambda _name: self.fail(
                        "malformed supervisor snapshot reached config"),
                    process=lambda _pid: self.fail(
                        "malformed supervisor snapshot reached process"),
                    command=lambda *args: self.fail(
                        "malformed supervisor snapshot sent stop"),
                )
                with self.assertRaisesRegex(RuntimeError, reason):
                    stop(helper, name, script)

        # A valid positive PID still reaches the existing checked stop path.
        stopped = []
        helper = types.SimpleNamespace(
            service_state=lambda _name: {
                "state": "STOPPED" if stopped else "RUNNING", "pid": 321},
            program_config=lambda _name: {
                "command": "python " + str(script),
                "stopasgroup": "false", "killasgroup": "false"},
            process=lambda _pid: {
                "service": name, "argv": ["python", str(script)], "pgrp": 321},
            command=lambda argv, timeout: (
                (stopped.append(list(argv)) or 0), "stopped"),
        )
        self.assertIsNone(stop(helper, name, script))
        self.assertEqual(stopped, [["supervisorctl", "stop", name]])


    def test_stop_controller_rejects_untyped_config_and_process_identity(self):
        # Real stop_controller AST, synthetic Supervisor only: no native stop.
        stop = load_pinned_verifier(Path("/tmp"))["stop_controller"]
        name = "nox-dispatcher-t855u"
        script = Path("/root/nox/scripts/nox_dispatcher_t855u.py")
        valid_config = {"command": "python " + str(script),
                        "stopasgroup": "false", "killasgroup": "false"}
        valid_row = {"service": name, "argv": ["python", str(script)], "pgrp": 321}

        def attempt(config, row, census=None):
            sent, reads = [], []
            def service_state(_name):
                return {"state": "STOPPED" if sent else "RUNNING", "pid": 321}
            def process_table():
                reads.append("census")
                return census
            helper = types.SimpleNamespace(
                service_state=service_state,
                program_config=lambda _name: config,
                process=lambda _pid: row,
                process_table=process_table,
                command=lambda argv, timeout: (sent.append(list(argv)) or 0, "ok"))
            return lambda: stop(helper, name, script), sent, reads

        malformed_config = (
            None, [], "config", {},
            {"command": "python " + str(script)},
            {**valid_config, "command": None},
            {**valid_config, "command": []},
            {**valid_config, "command": "python 'unterminated"},
            {**valid_config, "stopasgroup": True},
            {**valid_config, "stopasgroup": None},
            {**valid_config, "stopasgroup": "FALSE"},
            {**valid_config, "killasgroup": False},
            {**valid_config, "killasgroup": ""},
        )
        for config in malformed_config:
            with self.subTest(config=repr(config)):
                run, sent, census_reads = attempt(config, valid_row)
                with self.assertRaisesRegex(RuntimeError, "HOLD_CONTROLLER_CONFIG_READBACK"):
                    run()
                self.assertEqual(sent, [])
                self.assertEqual(census_reads, [])

        malformed_process = (
            None, [], "process", {},
            {"service": name},
            {"service": name, "argv": str(script)},
            {"service": name, "argv": ["python", True, str(script)]},
            {"service": name, "argv": ["python", None, str(script)]},
            {"service": name, "argv": ("python", str(script))},
            {"service": "other", "argv": ["python", str(script)]},
            {"service": name, "argv": ["python", "/tmp/not-the-controller.py"]},
        )
        for row in malformed_process:
            with self.subTest(process=repr(row)):
                run, sent, census_reads = attempt(valid_config, row)
                with self.assertRaisesRegex(RuntimeError, "HOLD_CONTROLLER_IDENTITY"):
                    run()
                self.assertEqual(sent, [])
                self.assertEqual(census_reads, [])

        run, sent, reads = attempt(valid_config, valid_row)
        self.assertIsNone(run())
        self.assertEqual(sent, [["supervisorctl", "stop", name]])
        self.assertEqual(reads, [])

        own = {"self": {"pgrp": 321, "state": "S", "service": name}}
        for flag in ("stopasgroup", "killasgroup"):
            with self.subTest(group_flag=flag):
                run, sent, reads = attempt({**valid_config, flag: "true"},
                                           valid_row, own)
                self.assertIsNone(run())
                self.assertEqual(sent, [["supervisorctl", "stop", name]])
                self.assertEqual(reads, ["census"])

        foreign = {**own, "foreign": {"pgrp": 321, "state": "S",
                                      "service": "other-controller"}}
        run, sent, reads = attempt({**valid_config, "stopasgroup": "true"},
                                   valid_row, foreign)
        with self.assertRaisesRegex(RuntimeError, "HOLD_CONTROLLER_FOREIGN_PROCESS_GROUP"):
            run()
        self.assertEqual(sent, [])
        self.assertEqual(reads, ["census"])

    def test_group_stop_requires_unambiguous_native_census(self):
        # AST-execute actual stop_controller with synthetic process snapshots.
        stop = load_pinned_verifier(Path("/tmp"))["stop_controller"]
        name = "nox-dispatcher-t855u"
        script = Path("/root/nox/scripts/nox_dispatcher_t855u.py")

        def attempt(census, process_pgrp=321):
            sent = []
            def state(_name):
                return {"state": "STOPPED" if sent else "RUNNING", "pid": 321}
            helper = types.SimpleNamespace(
                service_state=state,
                program_config=lambda _name: {
                    "command": "python " + str(script),
                    "stopasgroup": "true", "killasgroup": "false"},
                process=lambda _pid: {
                    "service": name, "argv": ["python", str(script)],
                    "pgrp": process_pgrp},
                process_table=lambda: census,
                command=lambda argv, timeout: (sent.append(argv) or 0, "ok"),
            )
            return lambda: stop(helper, name, script), sent

        own = {"pgrp": 321, "state": "S", "service": name}
        invalid = (
            (None, 321), ([], 321), ({}, 321),
            ({"self": None}, 321),
            ({"self": {"pgrp": True, "state": "S", "service": name}}, 321),
            ({"self": {"state": "S", "service": name}}, 321),
            ({"self": {"pgrp": 321, "state": None, "service": name}}, 321),
            ({"self": {"pgrp": 321, "state": "S"}}, 321),
            ({"self": own}, True),
            ({"self": own}, None),
        )
        for census, pgrp in invalid:
            with self.subTest(census=repr(census), process_pgrp=repr(pgrp)):
                run, sent = attempt(census, pgrp)
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_CONTROLLER_PROCESS_GROUP_READBACK"):
                    run()
                self.assertEqual(sent, [])

        for census in (
            {"self": own},
            {"self": own, "other": {"pgrp": 444, "state": "S",
                                      "service": "unrelated"}},
            {"self": own, "zombie": {"pgrp": 321, "state": "Z",
                                       "service": "foreign"}},
        ):
            with self.subTest(healthy=repr(census)):
                run, sent = attempt(census)
                self.assertIsNone(run())
                self.assertEqual(sent, [["supervisorctl", "stop", name]])

        run, sent = attempt({
            "self": own, "foreign": {"pgrp": 321, "state": "S",
                                     "service": "foreign"}})
        with self.assertRaisesRegex(
                RuntimeError, "HOLD_CONTROLLER_FOREIGN_PROCESS_GROUP"):
            run()
        self.assertEqual(sent, [])


    def test_post_stop_supervisor_readback_requires_valid_terminal_state(self):
        # Source-only, AST-executed. A successful stop command alone cannot
        # certify that the named controller is actually STOPPED/EXITED.
        stop = load_pinned_verifier(Path("/tmp"))["stop_controller"]
        name = "nox-dispatcher-t855u"
        script = Path("/root/nox/scripts/nox_dispatcher_t855u.py")
        malformed = (None, [], "STOPPED", {}, {"state": None},
                     {"state": "RUNNING"}, {"state": "FATAL"},
                     {"state": "STARTING"}, {"state": 0})
        for post in (*malformed, {"state": "STOPPED"}, {"state": "EXITED"}):
            with self.subTest(post=repr(post)):
                calls = []
                snapshots = []
                def service_state(_name):
                    snapshots.append(_name)
                    return ({"state": "RUNNING", "pid": 321}
                            if len(snapshots) == 1 else post)
                def command(argv, timeout):
                    calls.append((argv, timeout))
                    return (0, "ok")
                helper = types.SimpleNamespace(
                    service_state=service_state,
                    program_config=lambda _name: {
                        "command": "python " + str(script),
                        "stopasgroup": "false", "killasgroup": "false"},
                    process=lambda _pid: {
                        "service": name, "argv": ["python", str(script)],
                        "pgrp": 321},
                    command=command,
                )
                if isinstance(post, dict) and post.get("state") in ("STOPPED", "EXITED"):
                    self.assertIsNone(stop(helper, name, script))
                else:
                    with self.assertRaisesRegex(RuntimeError, "HOLD_CONTROLLER_STOP_FAILED"):
                        stop(helper, name, script)
                self.assertEqual(calls, [(["supervisorctl", "stop", name], 75)])
                self.assertEqual(snapshots, [name, name])


    def test_owner_pause_at_target_never_claims_completed_continuation(self):
        # A verified 1000-step owner STOP is a checkpoint, not proof that the
        # native continuation emitted VERIFIED_BOUNDED_ADAPTER_UPDATE.
        classify = load_pinned_verifier(Path("/tmp"))["continuation_terminal_state"]
        paused = {"state": "CHECKPOINTED_OWNER_STOP", "global_step": 1000}
        done = {"state": "VERIFIED_BOUNDED_ADAPTER_UPDATE", "global_step": 1000}
        self.assertEqual(classify(paused), "CONTINUATION_CHECKPOINTED_BY_OWNER_PAUSE")
        self.assertEqual(classify(done), "CONTINUATION_TARGET_1000_COMPLETED")
        self.assertEqual(classify({**done, "global_step": 999}),
                         "CONTINUATION_CHECKPOINTED_BY_OWNER_PAUSE")
        self.assertEqual(classify({**done, "global_step": True}),
                         "CONTINUATION_CHECKPOINTED_BY_OWNER_PAUSE")
        # Protect against a correct but unused helper: real main() must call it.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        self.assertTrue(any(isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Name)
                            and n.func.id == "continuation_terminal_state"
                            for n in ast.walk(main)))


    def test_initial_checkpoint_rejects_optimizer_step_underreport(self):
        # A valid checkpoint step=2 with only one claimed optimizer update
        # cannot prove the first two optimizer steps were actually performed.
        # All files and SHA-256 receipts are valid in this fixture.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            verifier = load_pinned_verifier(root)
            checkpoint = root / "checkpoint-2"
            checkpoint.mkdir()
            (checkpoint / "adapter_model.safetensors").write_bytes(b"tensor-after-two")
            (checkpoint / "trainer_state.json").write_text(
                '{"global_step":2}', encoding="utf-8")
            names = ("adapter_model.safetensors", "trainer_state.json")
            hashes = {name: verifier["file_sha"](checkpoint / name) for name in names}
            receipt = {
                "global_step": 2, "state": "CHECKPOINTED_OWNER_STOP",
                "native_sha256": "a" * 64,
                "successful_optimizer_steps": 2,
                "adapter_delta_verified": True, "loss": 0.4,
                "before_tensor_sha256": "b" * 64,
                "after_tensor_sha256": "c" * 64,
                "checkpoint": {"path": str(checkpoint),
                               "global_step": 2, "files_sha256": hashes},
            }
            helper = types.SimpleNamespace(CHECKPOINT_NAMES=names)
            self.assertTrue(verifier["verify_paused_result"](helper, receipt))
            receipt["successful_optimizer_steps"] = 1
            with self.assertRaisesRegex(RuntimeError,
                                        "HOLD_PAUSED_OPTIMIZER_RECEIPT"):
                verifier["verify_paused_result"](helper, receipt)


    def test_bounded_json_state_rejects_descriptor_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read_json = load_pinned_verifier(root)["read_json"]
            safe = root / "safe.json"
            safe.write_text('{"global_step": 1}', encoding="utf-8")
            self.assertEqual(read_json(safe, limit=64), {"global_step": 1})

            # A correct SHA-256 signs bytes, not their JSON validity. Corrupt
            # native checkpoint state must HOLD instead of leaking decoder errors.
            malformed = root / "malformed-signed-state.json"
            for raw in (b'{"global_step":', b'{"global_step": 1,}',
                        b'\xff{"global_step": 1}'):
                with self.subTest(signed_malformed=repr(raw)):
                    malformed.write_bytes(raw)
                    signed_sha = hashlib.sha256(raw).hexdigest()
                    with self.assertRaisesRegex(
                            RuntimeError, "^HOLD_INVALID_STATE_JSON$"):
                        read_json(malformed, limit=128,
                                  expected_sha256=signed_sha)

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


    def test_bounded_json_rejects_growth_during_single_descriptor_read(self):
        # Even without a receipt SHA, appended whitespace is valid JSON.
        # The preimage returned a parsed state although the inode changed
        # between fstat and read. Only a stable descriptor can be accepted.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "trainer_state.json"
            state.write_text('{"global_step":1}', encoding="utf-8")
            read_json = load_pinned_verifier(root)["read_json"]
            self.assertEqual(read_json(state, limit=64), {"global_step": 1})
            real_fdopen = os.fdopen

            class AppendWhitespaceOnRead:
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
                        with state.open("ab") as writer:
                            writer.write(b"  ")
                    return self.stream.read(size)

            def fdopen_with_append(fd, mode):
                return AppendWhitespaceOnRead(real_fdopen(fd, mode))

            with mock.patch("os.fdopen", side_effect=fdopen_with_append):
                with self.assertRaisesRegex(RuntimeError, "HOLD_STATE_FILE_MUTATED"):
                    read_json(state, limit=64)


    def test_json_exponent_overflow_fails_closed_with_signed_sha(self):
        # parse_constant rejects literal NaN/Infinity, but json.loads
        # converts valid JSON numeric exponents like 1e999 to float('inf').
        # A matching signed checkpoint SHA must not legalize that value.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read_json = load_pinned_verifier(root)["read_json"]
            state = root / "trainer_state.json"
            for document in (
                '{"global_step":1,"loss":1e999}',
                '{"global_step":1,"loss":-1e999}',
                '{"global_step":1,"history":[0.4,1e100000]}',
            ):
                with self.subTest(document=document):
                    raw = document.encode("utf-8")
                    state.write_bytes(raw)
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_NONFINITE_STATE_JSON"):
                        read_json(state, limit=128,
                                  expected_sha256=hashlib.sha256(raw).hexdigest())
            valid = b'{"global_step":1,"loss":0.25}'
            state.write_bytes(valid)
            self.assertEqual(read_json(
                state, limit=128, expected_sha256=hashlib.sha256(valid).hexdigest()
            )["loss"], 0.25)


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


    def test_final_receipt_uses_live_proxy_8080_not_retired_8081(self):
        # The final receipt used to check 8081, a retired/closed port, even
        # when resource admission had verified healthy serving on 8080.
        # Execute only the actual final If AST: no trainer, service or S03.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        health = [
            node for node in ast.walk(main)
            if isinstance(node, ast.If)
            and "result['chat_after'].get(" in ast.unparse(node.test)
        ]
        self.assertEqual(len(health), 1)
        predicate = ast.unparse(health[0].test)
        self.assertIn("type(result['chat_after']) is not dict", predicate)
        self.assertIn("type(result['chat_after'].get('8080')) is not int", predicate)
        self.assertIn("result['chat_after']['8080'] != 200", predicate)
        self.assertNotIn("'8081'", predicate)
        isolated = ast.Module(body=[copy.deepcopy(health[0])], type_ignores=[])
        compiled = compile(ast.fix_missing_locations(isolated), str(SOURCE), "exec")

        healthy = {"result": {"chat_after": {"8080": 200,
                                               "8081": "ConnectionRefusedError"}},
                   "success": True}
        exec(compiled, healthy)
        self.assertTrue(healthy["success"])
        self.assertNotIn("chat_health_regression", healthy["result"])

        # A healthy 8081 cannot conceal failure of the real chat proxy.
        degraded = {"result": {"chat_after": {"8080": "ConnectionRefusedError",
                                                "8081": 200}}, "success": True}
        exec(compiled, degraded)
        self.assertFalse(degraded["success"])
        self.assertIs(degraded["result"]["chat_health_regression"], True)


    def test_resource_admission_fails_closed_on_gpu_census_and_supervisor_shape(self):
        # Exact source function; all probes are synthetic, never a live GPU.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text(
                "TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            admit = load_pinned_verifier(root)["resource_admission"]
            inputs = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",
            }
            def fake_read_text(path, *args, **kwargs):
                return inputs[str(path)]
            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=lambda *args: {"train_cpu_gib": 64},
                health=lambda: {"8080": 200},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(admit(helper)["gpu1"]["free_mib"], 30000)
                for malformed in (None, [], {}, {"state": None},
                                  {"state": True}, {"state": ["STOPPED"]}):
                    with self.subTest(supervisor=malformed):
                        helper.service_state = lambda value=malformed: value
                        with self.assertRaisesRegex(
                                RuntimeError, "HOLD_TRAINER_STATE_READBACK"):
                            admit(helper)
                helper.service_state = lambda: {"state": "STOPPED"}
                valid = {"index": 1, "free_mib": 30000}
                for malformed in (
                    None, [], {}, {"gpus": None}, {"gpus": {}},
                    {"gpus": [None]}, {"gpus": []},
                    {"gpus": [{"index": True, "free_mib": 30000}]},
                    {"gpus": [{"index": 1, "free_mib": True}]},
                    {"gpus": [{"index": 1, "free_mib": "30000"}]},
                    {"gpus": [{"index": 1, "free_mib": -1}]},
                    {"gpus": [{"index": 0, "free_mib": 30000}]},
                    {"gpus": [valid, valid]},
                ):
                    with self.subTest(gpu=malformed):
                        helper.gpu = lambda value=malformed: value
                        with self.assertRaisesRegex(
                                RuntimeError, "HOLD_GPU1_CENSUS_READBACK"):
                            admit(helper)
                helper.gpu = lambda: {"gpus": [{"index": 1, "free_mib": 26000}]}
                with self.assertRaisesRegex(RuntimeError, "HOLD_GPU1_HEADROOM"):
                    admit(helper)

    def test_resource_budget_readback_refuses_ambiguous_headroom(self):
        # Execute the exact owner resource admission AST with synthetic cgroup
        # and GPU probes only; no native trainer, lease or model is touched.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text(
                "TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            admit = load_pinned_verifier(root)["resource_admission"]
            contents = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",
            }
            def fake_read_text(path, *args, **kwargs):
                return contents[str(path)]
            budget_value = {"train_cpu_gib": 64}
            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=lambda *_: budget_value,
                health=lambda: {"8080": 200},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(admit(helper)["budget"]["train_cpu_gib"], 64)
                for invalid in (None, [], True, {}, {"train_cpu_gib": None},
                                {"train_cpu_gib": True},
                                {"train_cpu_gib": "64"},
                                {"train_cpu_gib": 64.0},
                                {"train_cpu_gib": float("nan")},
                                {"train_cpu_gib": float("inf")},
                                {"train_cpu_gib": -1},
                                {"train_cpu_gib": 1000000000}):
                    with self.subTest(budget=invalid):
                        budget_value = invalid
                        with self.assertRaisesRegex(
                                RuntimeError, "HOLD_RESOURCE_BUDGET_READBACK"):
                            admit(helper)
                budget_value = {"train_cpu_gib": 63}
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_INSTALLED_TRAIN_CPU_RAM_HEADROOM"):
                    admit(helper)

    def test_resource_admission_requires_actual_proxy_8080_not_legacy_8081(self):
        # Owner-confirmed 2026-11-19: proxy /health=200 on 8080; 8081 closed.
        # This source-only test never contacts the host or starts training.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            verifier = load_pinned_verifier(root)["resource_admission"]

            def fake_read_text(path, *args, **kwargs):
                contents = {
                    "/sys/fs/cgroup/cpu.max": "400000 100000",
                    "/sys/fs/cgroup/memory.max": "194065203200",
                    "/sys/fs/cgroup/memory.current": "188662734848",

                }
                return contents[str(path)]

            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=lambda *args: {"train_cpu_gib": 64},
                health=lambda: {"8080": 200, "8081": "ConnectionRefusedError"},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                admitted = verifier(helper)
                self.assertEqual(admitted["budget"]["configured_train_cpu_gib"], 64)
                # Legacy 8081 cannot stand in for failed actual serving.
                helper.health = lambda: {"8080": "ConnectionRefusedError", "8081": 200}
                with self.assertRaisesRegex(RuntimeError, "HOLD_CHAT_HEALTH_BEFORE_TRAINING"):
                    verifier(helper)


    def test_resource_admission_cgroup_v2_unlimited_cpu_quota(self):
        # 'max PERIOD' is a valid cgroup v2 cpu.max state, not a parse error.
        # No host cgroup/lease/GPU/model access or native training is performed.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            verifier = load_pinned_verifier(root)["resource_admission"]
            sources = {
                "/sys/fs/cgroup/cpu.max": "max 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",

            }
            cpu_calls = []

            def fake_read_text(path, *args, **kwargs):
                return sources[str(path)]

            def budget(mem_max, mem_current, quota_cpus, affinity_cpus):
                cpu_calls.append((quota_cpus, affinity_cpus))
                return {"train_cpu_gib": 64}

            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=budget,
                health=lambda: {"8080": 200},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(verifier(helper)["budget"]["configured_train_cpu_gib"], 64)
                self.assertEqual(cpu_calls[-1], (4, 4))
                sources["/sys/fs/cgroup/cpu.max"] = "400000 100000"
                verifier(helper)
                self.assertEqual(cpu_calls[-1], (4, 4))
                # More quota than sched_getaffinity does NOT mean 8 usable
                # CPUs: over-admission can steal budget from live serving.
                sources["/sys/fs/cgroup/cpu.max"] = "800000 100000"
                verifier(helper)
                self.assertEqual(cpu_calls[-1], (4, 4))
                sources["/sys/fs/cgroup/cpu.max"] = "100000 100000"
                verifier(helper)
                self.assertEqual(cpu_calls[-1], (1, 4))
                # Regression: preimage rounded 0.5 or 0.00001 CPU up to a
                # falsely admitted full CPU and overstated the chat budget.
                for invalid in ("max 0", "0 100000", "bogus 100000",
                                "max", "max 100000 extra", "max -1",
                                "50000 100000", "1 100000", "99999 100000"):
                    with self.subTest(cpu_max=invalid):
                        sources["/sys/fs/cgroup/cpu.max"] = invalid
                        with self.assertRaisesRegex(RuntimeError, "HOLD_CGROUP_CPU_QUOTA"):
                            verifier(helper)

    def test_resource_admission_cgroup_memory_max_fails_closed(self):
        # Linux cgroup v2 reports no memory ceiling as "max". Neither
        # unbounded nor corrupt usage may be admitted as measured RAM.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            verify = load_pinned_verifier(root)["resource_admission"]
            maximum = 194065203200
            sources = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": str(maximum),
                "/sys/fs/cgroup/memory.current": "188662734848",

            }
            admitted_budgets = []

            def fake_read_text(path, *args, **kwargs):
                return sources[str(path)]

            def budget(limit, current, quota, affinity):
                admitted_budgets.append((limit, current, quota, affinity))
                return {"train_cpu_gib": 64}

            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=budget,
                health=lambda: {"8080": 200},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(verify(helper)["budget"]["configured_train_cpu_gib"], 64)
                self.assertEqual(admitted_budgets, [
                    (maximum, 188662734848, 4, 4)])
                for memory_max in ("max", "0", "-1", "broken", ""):
                    with self.subTest(memory_max=memory_max):
                        sources["/sys/fs/cgroup/memory.max"] = memory_max
                        with self.assertRaisesRegex(RuntimeError, "HOLD_CGROUP_MEMORY_LIMIT"):
                            verify(helper)
                sources["/sys/fs/cgroup/memory.max"] = str(maximum)
                for memory_current in ("max", "broken", str(maximum + 1)):
                    with self.subTest(memory_current=memory_current):
                        sources["/sys/fs/cgroup/memory.current"] = memory_current
                        with self.assertRaisesRegex(RuntimeError, "HOLD_CGROUP_MEMORY_LIMIT"):
                            verify(helper)
                # No invalid cgroup snapshot reaches the native resource
                # budget calculator; proxy/model/weights are untouched.
                self.assertEqual(len(admitted_budgets), 1)


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



    def test_checkpoint_hash_rejects_path_rebind_during_open_read(self):
        # Previous file_sha hashed a stable descriptor, but its pathname
        # could be rebound to another inode while hashing and still pass.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "adapter_model.safetensors"
            replacement = root / "replacement.safetensors"
            original = b"checkpoint-a"
            changed = b"checkpoint-b"
            path.write_bytes(original)
            replacement.write_bytes(changed)
            file_sha = load_pinned_verifier(root)["file_sha"]
            self.assertEqual(file_sha(path), hashlib.sha256(original).hexdigest())
            real_fdopen = os.fdopen

            class RenameBetweenOpenAndRead:
                def __init__(self, stream):
                    self.stream = stream
                    self.rebound = False

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def fileno(self):
                    return self.stream.fileno()

                def read(self, n):
                    if not self.rebound:
                        self.rebound = True
                        os.replace(path, root / "old-inode.safetensors")
                        os.replace(replacement, path)
                    return self.stream.read(n)

            with mock.patch("os.fdopen", side_effect=lambda fd, mode:
                            RenameBetweenOpenAndRead(real_fdopen(fd, mode))):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_CHECKPOINT_FILE_MUTATED"):
                    file_sha(path)
            self.assertEqual(path.read_bytes(), changed)
            self.assertEqual((root / "old-inode.safetensors").read_bytes(), original)




    def test_bounded_json_rejects_path_rebind_during_read(self):
        # A writer can rename a stable, SHA-matching descriptor and bind a
        # different state file to the path while read_json is still reading.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "trainer_state.json"
            replacement = root / "replacement.json"
            original = b'{"global_step":1}'
            changed = b'{"global_step":2}'
            state.write_bytes(original)
            replacement.write_bytes(changed)
            read_json = load_pinned_verifier(root)["read_json"]
            expected_sha = hashlib.sha256(original).hexdigest()
            self.assertEqual(read_json(state, limit=64,
                                       expected_sha256=expected_sha),
                             {"global_step": 1})
            real_fdopen = os.fdopen

            class RebindOnRead:
                def __init__(self, stream):
                    self.stream = stream
                    self.rebound = False

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def fileno(self):
                    return self.stream.fileno()

                def read(self, n):
                    if not self.rebound:
                        self.rebound = True
                        os.replace(state, root / "old-state.json")
                        os.replace(replacement, state)
                    return self.stream.read(n)

            with mock.patch("os.fdopen", side_effect=lambda fd, mode:
                            RebindOnRead(real_fdopen(fd, mode))):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_STATE_FILE_MUTATED"):
                    read_json(state, limit=64, expected_sha256=expected_sha)
            self.assertEqual(state.read_bytes(), changed)
            self.assertEqual((root / "old-state.json").read_bytes(), original)


    def test_owned_training_hold_flag_is_bound_to_stable_regular_descriptor(self):
        # The old is_symlink/is_file/stat then read_text sequence allowed an
        # inode/symlink swap between policy precheck and owner flag read.
        # No native flag is touched: this is a temporary isolated fixture.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flag = root / "TRAIN_HOLD.flag"
            prefix = "OWNER_REQUESTED_TRAINING_HALT request=3 source=abc"
            flag.write_text(prefix + "\n", encoding="utf-8")
            verify = load_pinned_verifier(root)["owned_flag"]
            self.assertIsNone(verify(flag, prefix))

            alias = root / "owner-alias.flag"
            alias.symlink_to(flag)
            with self.assertRaisesRegex(RuntimeError, "HOLD_CURRENT_OWNER_FLAG_CHANGED"):
                verify(alias, prefix)
            fifo = root / "owner-fifo.flag"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(RuntimeError, "HOLD_CURRENT_OWNER_FLAG_CHANGED"):
                verify(fifo, prefix)

            replacement = root / "replacement.flag"
            replacement.write_text(prefix + "\n", encoding="utf-8")
            actual_fdopen = os.fdopen

            class RebindOnOwnerFlagRead:
                def __init__(self, stream):
                    self.stream = stream
                    self.rebound = False

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def fileno(self):
                    return self.stream.fileno()

                def read(self, length):
                    if not self.rebound:
                        self.rebound = True
                        os.replace(flag, root / "old-owner.flag")
                        flag.symlink_to(replacement)
                    return self.stream.read(length)

            with mock.patch("os.fdopen", side_effect=lambda fd, mode:
                            RebindOnOwnerFlagRead(actual_fdopen(fd, mode))):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_CURRENT_OWNER_FLAG_CHANGED"):
                    verify(flag, prefix)
            self.assertTrue(flag.is_symlink())
            self.assertEqual((root / "old-owner.flag").read_text(),
                             prefix + "\n")


    def test_train_cpu_env_rejects_extra_directives_after_valid_cap(self):
        # Previous MULTILINE findall accepted an approved first line
        # despite trailing shell/env directives that the trainer could load.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            admit = load_pinned_verifier(root)["resource_admission"]
            sources = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",

            }
            def fake_read_text(path, *args, **kwargs):
                return sources[str(path)]
            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=lambda *args: {"train_cpu_gib": 64},
                health=lambda: {"8080": 200},
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(admit(helper)["budget"]["configured_train_cpu_gib"], 64)
                for invalid in (
                    "TRAIN_CPU_MAX=64GiB\nEXTRA=1\n",
                    "TRAIN_CPU_MAX=64GiB\n# innocent-looking appended comment\n",
                    "TRAIN_CPU_MAX=64GiB\nexport TRAIN_CPU_MAX=1GiB\n",
                    "TRAIN_CPU_MAX=64GiB\nTRAIN_CPU_MAX=64GiB\n",
                    "TRAIN_CPU_MAX=64GiB\n\n",
                ):
                    with self.subTest(contents=invalid):
                        (root / "train_cpu_max.env").write_text(invalid, encoding="utf-8")
                        with self.assertRaisesRegex(RuntimeError, "HOLD_INSTALLED_TRAIN_CPU_LIMIT"):
                            admit(helper)



    def test_train_cpu_env_cap_rejects_symlink_fifo_and_non_regular_bytes(self):
        # An approved target behind a symlink previously passed read_text().
        # O_NOFOLLOW must fence it; O_NONBLOCK must not hang on a FIFO.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cap = load_pinned_verifier(root)["read_installed_train_cpu_cap"]
            env = root / "train_cpu_max.env"
            env.write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            self.assertEqual(cap(env), 64)
            env.unlink()
            target = root / "approved.env"
            target.write_text("TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            env.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "HOLD_INSTALLED_TRAIN_CPU_LIMIT"):
                cap(env)
            env.unlink()
            os.mkfifo(env)
            with self.assertRaisesRegex(RuntimeError, "HOLD_INSTALLED_TRAIN_CPU_LIMIT"):
                cap(env)
            env.unlink()
            env.write_bytes(b"TRAIN_CPU_MAX=64GiB\nEXTRA=1")
            with self.assertRaisesRegex(RuntimeError, "HOLD_INSTALLED_TRAIN_CPU_LIMIT"):
                cap(env)



    def test_start_once_checks_late_global_stop_before_supervisor_start(self):
        # Pure AST-isolated nested function. No supervisor or real STOP touched.
        # The former source ran the start command even if STOP was latched
        # after resource_admission() and release_flags().
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        start = next(n for n in main.body
                     if isinstance(n, ast.FunctionDef) and n.name == "start_once")
        starts, receipts = [], []
        helper = types.SimpleNamespace(
            command=lambda argv, timeout: (starts.append((argv, timeout)) or (0, "")),
            service_state=lambda: {"state": "RUNNING", "pid": 1},
        )
        context = {
            "helper": helper, "global_stop": lambda: True,
            "SERVICE": "nox-train-volta-t866u",
            "result": {"training_started": False},
            "prove_training": lambda _: {"pid": 1},
            "step": lambda kind, data: receipts.append((kind, data)),
        }
        exec(compile(ast.Module(body=[start], type_ignores=[]), str(SOURCE), "exec"),
             context)
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            context["start_once"](5)
        self.assertEqual(starts, [])
        self.assertEqual(receipts, [])
        self.assertFalse(context["result"]["training_started"])

        # No change to the owner-admitted path when global STOP is absent.
        context["global_stop"] = lambda: False
        context["start_once"](5)
        self.assertEqual(starts, [
            (["supervisorctl", "start", "nox-train-volta-t866u"], 35)
        ])
        self.assertTrue(context["result"]["training_started"])
        self.assertEqual(receipts[0][0], "single_native_training_started")




    def test_controller_restart_readback_is_bounded_and_fail_closed(self):
        # Execute only the actual post-maintenance restart loop from main():
        # no controller, Supervisor, trainer, or server is contacted.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        matches = [node for node in ast.walk(tree) if isinstance(node, ast.For)
                   and "controllers_stopped.remove(name)" in ast.unparse(node)
                   and "supervisorctl" in ast.unparse(node)]
        self.assertEqual(len(matches), 1)
        code = compile(ast.Module(body=[copy.deepcopy(matches[0])], type_ignores=[]),
                       "<isolated-restart-loop>", "exec")

        def attempt(status, rc=0):
            calls = []
            class FakeHelper:
                def command(self, args, timeout):
                    calls.append(("command", args, timeout))
                    return rc, ""
                def service_state(self, name):
                    calls.append(("state", name))
                    return status
            scope = {"controllers_stopped": ["owner-controller"], "helper": FakeHelper()}
            try:
                exec(code, scope)
            except RuntimeError as exc:
                return str(exc), scope["controllers_stopped"], calls
            return None, scope["controllers_stopped"], calls

        invalid = (None, [], "", 2, False, {}, {"state": None},
                   {"state": False}, {"state": []}, {"state": "STOPPED"})
        for snapshot in invalid:
            with self.subTest(snapshot=snapshot):
                error, stopped, calls = attempt(snapshot)
                self.assertEqual(error, "HOLD_CONTROLLER_RESTART")
                self.assertEqual(stopped, ["owner-controller"])
                self.assertEqual(calls[0], ("command",
                    ["supervisorctl", "start", "owner-controller"], 30))
        for state in ("RUNNING", "STARTING"):
            with self.subTest(state=state):
                error, stopped, calls = attempt({"state": state})
                self.assertIsNone(error)
                self.assertEqual(stopped, [])
                self.assertEqual(len(calls), 2)
        error, stopped, calls = attempt({"state": "RUNNING"}, rc=1)
        self.assertEqual(error, "HOLD_CONTROLLER_RESTART")
        self.assertEqual(stopped, ["owner-controller"])
        self.assertEqual(len(calls), 1)  # nonzero start result is never readback proof

    def test_start_once_invalid_supervisor_shape_fails_closed_initial_and_poll(self):
        # Extract the actual nested function; never contact native Supervisor.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        start = next(node for node in main.body
                     if isinstance(node, ast.FunctionDef) and node.name == "start_once")
        code = compile(ast.Module(body=[start], type_ignores=[]), str(SOURCE), "exec")

        def scenario(replies):
            start_calls, proofs, receipts, sleeps = [], [], [], []
            iterator = iter(replies)
            helper = types.SimpleNamespace(
                command=lambda args, timeout: (start_calls.append((args, timeout)) or (0, "")),
                service_state=lambda: next(iterator))
            ctx = {
                "helper": helper, "global_stop": lambda: False,
                "SERVICE": "nox-train-volta-t866u",
                "time": types.SimpleNamespace(monotonic=lambda: 0,
                                              sleep=lambda delay: sleeps.append(delay)),
                "result": {"training_started": False},
                "prove_training": lambda _: (proofs.append("identified") or {"pid": 123}),
                "step": lambda kind, data: receipts.append((kind, data)),
            }
            exec(code, ctx)
            return ctx["start_once"], ctx["result"], start_calls, proofs, receipts, sleeps

        malformed = (None, [], "RUNNING", {}, {"pid": 123},
                     {"state": None}, {"state": []}, {"state": False},
                     {"state": {"nested": "RUNNING"}})
        for bad in malformed:
            for replies in ([bad], [{"state": "STARTING"}, bad]):
                with self.subTest(reply=repr(bad), mid_poll=len(replies) == 2):
                    start_once, result, calls, proofs, receipts, sleeps = scenario(replies)
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_NEW_TRAINER_STATUS_READBACK"):
                        start_once(5)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(proofs, [])
                    self.assertEqual(receipts, [])
                    self.assertFalse(result["training_started"])
                    self.assertEqual(sleeps, [0.5] if len(replies) == 2 else [])

        start_once, result, calls, proofs, receipts, sleeps = scenario(
            [{"state": "STARTING"}, {"state": "RUNNING", "pid": 123}])
        start_once(5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(proofs, ["identified"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0][0], "single_native_training_started")
        self.assertTrue(result["training_started"])
        self.assertEqual(sleeps, [0.5])

    def test_failed_supervisor_start_cannot_claim_existing_running_service(self):
        # A stale RUNNING status cannot legitimize a failed start command.
        # This is AST-isolated; no native service or persistent flag is touched.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        start = next(node for node in main.body
                     if isinstance(node, ast.FunctionDef) and node.name == "start_once")
        starts, evidence = [], []
        helper = types.SimpleNamespace(
            command=lambda argv, timeout: (starts.append(argv) or (7, "already running")),
            service_state=lambda: {"state": "RUNNING", "pid": 123},
        )
        namespace = {
            "helper": helper, "global_stop": lambda: False, "SERVICE": "nox-train-volta-t866u",
            "result": {"training_started": False},
            "prove_training": lambda _: {"pid": 123},
            "step": lambda kind, data: evidence.append((kind, data)),
        }
        exec(compile(ast.Module(body=[start], type_ignores=[]), str(SOURCE), "exec"),
             namespace)
        with self.assertRaisesRegex(RuntimeError, "HOLD_SINGLE_TRAINER_START_FAILED"):
            namespace["start_once"](5)
        self.assertEqual(starts, [["supervisorctl", "start", "nox-train-volta-t866u"]])
        self.assertFalse(namespace["result"]["training_started"])
        self.assertEqual(evidence, [])


    def test_owned_flag_requires_source_token_boundary_before_release(self):
        # An owner prefix ending in a hash must not match a longer, foreign
        # source token. This test does not rename, release or touch live flags.
        with tempfile.TemporaryDirectory() as folder:
            flag = Path(folder) / "TRAIN_HOLD.flag"
            prefix = "OWNER_REQUESTED_TRAINING_HALT request=3 source=" + "a" * 40
            owned = load_pinned_verifier(Path(folder))["owned_flag"]
            for valid in (prefix + "\n", prefix + " reason=owner_confirmed\n"):
                flag.write_text(valid, encoding="utf-8")
                self.assertIsNone(owned(flag, prefix))
            for foreign in (prefix + "f\n", prefix + "_different_owner\n",
                            prefix + "\tappended_without_approved_boundary\n"):
                with self.subTest(foreign=foreign):
                    flag.write_text(foreign, encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_CURRENT_OWNER_FLAG_CHANGED"):
                        owned(flag, prefix)
                    self.assertEqual(flag.read_text(encoding="utf-8"), foreign)



    def test_injected_permission_helper_is_descriptor_bound_and_fail_closed(self):
        # Extract the literal that is installed into existing controllers.
        # No native policy, supervisor or training state is touched.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        item = next(node for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and
                            target.id == "PERMISSION_HELPER" for target in node.targets))
        embedded = ast.literal_eval(item.value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            policy = state / "task_boost_mode.json"
            valid = {
                "enabled": True, "mode": "TASK_BOOST",
                "training_allowed": True,
                "training_service": "nox-train-volta-t866u",
                "training_request": "__NOX_OWNER_REQUEST_ID__",
                "training_source_sha": "__NOX_OWNER_SOURCE_SHA__",
            }
            policy.write_text(json.dumps(valid), encoding="utf-8")
            scope = {"ROOT": root}
            exec(compile(embedded, "<isolated-permission-helper>", "exec"), scope)
            allowed = scope["_nox_owner_training_allowed"]
            self.assertTrue(allowed())

            policy.write_text(json.dumps({**valid, "training_allowed": False}),
                              encoding="utf-8")
            self.assertFalse(allowed())
            policy.write_text(json.dumps(valid), encoding="utf-8")

            # Only the approved regular pathname is admissible.
            foreign = root / "other-policy.json"
            foreign.write_text(json.dumps(valid), encoding="utf-8")
            policy.unlink()
            policy.symlink_to(foreign)
            self.assertFalse(allowed())
            policy.unlink()
            os.mkfifo(policy)
            self.assertFalse(allowed())
            policy.unlink()
            policy.write_text("x" * 16001, encoding="utf-8")
            self.assertFalse(allowed())
            policy.write_text(json.dumps(valid), encoding="utf-8")

            # Rebind after open, before descriptor read: a stale inode and
            # replacement symlink cannot authorize this control-plane gate.
            old_read = os.read
            previous = root / "original-policy.json"
            read_count = []

            def swap_during_read(fd, size):
                read_count.append(size)
                os.replace(policy, previous)
                policy.symlink_to(foreign)
                return old_read(fd, size)

            with mock.patch("os.read", side_effect=swap_during_read):
                self.assertFalse(allowed())
            self.assertEqual(read_count, [16001])
            self.assertTrue(policy.is_symlink())
            self.assertEqual(json.loads(previous.read_text(encoding="utf-8")), valid)


    def test_permission_helper_rejects_duplicate_authority_keys(self):
        # Strict parser: a valid owner policy succeeds, while last-value-wins
        # duplicates must not authorize a training service.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        item = next(node for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and
                            target.id == "PERMISSION_HELPER" for target in node.targets))
        embedded = ast.literal_eval(item.value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            policy = state / "task_boost_mode.json"
            valid = {"enabled": True, "mode": "TASK_BOOST",
                     "training_allowed": True,
                     "training_service": "nox-train-volta-t866u",
                      "training_request": "__NOX_OWNER_REQUEST_ID__",
                      "training_source_sha": "__NOX_OWNER_SOURCE_SHA__"}
            scope = {"ROOT": root}
            exec(compile(embedded, "<isolated-permission-helper>", "exec"), scope)
            allowed = scope["_nox_owner_training_allowed"]
            policy.write_text(json.dumps(valid), encoding="utf-8")
            self.assertTrue(allowed())
            for ambiguous in (
                '{"enabled":false,"enabled":true,"mode":"TASK_BOOST",'
                '"training_allowed":true,"training_service":"nox-train-volta-t866u"}',
                '{"enabled":true,"mode":"TASK_BOOST","training_allowed":false,'
                '"training_allowed":true,"training_service":"nox-train-volta-t866u"}',
                '{"enabled":true,"mode":"TASK_BOOST","training_allowed":true,'
                '"training_service":"other","training_service":"nox-train-volta-t866u"}',
            ):
                with self.subTest(ambiguous=ambiguous):
                    policy.write_text(ambiguous, encoding="utf-8")
                    self.assertFalse(allowed())
            policy.write_text(json.dumps(valid), encoding="utf-8")
            self.assertTrue(allowed())


    def test_permission_helper_refuses_nonfinite_json_in_any_policy_field(self):
        # Python json.loads accepts NaN/Infinity by default and turns 1e999
        # into float('inf'), while the canonical state reader forbids both.
        # A malformed owner policy must never authorize the training service.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        item = next(node for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and
                            target.id == "PERMISSION_HELPER" for target in node.targets))
        embedded = ast.literal_eval(item.value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "state").mkdir()
            policy = root / "state/task_boost_mode.json"
            valid = {"enabled": True, "mode": "TASK_BOOST",
                     "training_allowed": True,
                     "training_service": "nox-train-volta-t866u",
                      "training_request": "__NOX_OWNER_REQUEST_ID__",
                      "training_source_sha": "__NOX_OWNER_SOURCE_SHA__"}
            scope = {"ROOT": root}
            exec(compile(embedded, "<isolated-permission-helper>", "exec"), scope)
            allowed = scope["_nox_owner_training_allowed"]
            for invalid in ("NaN", "Infinity", "-Infinity", "1e999",
                            "-1e999", "[0, 1e100000]"):
                with self.subTest(invalid=invalid):
                    policy.write_text(
                        json.dumps(valid)[:-1] + ',"telemetry":' + invalid + '}',
                        encoding="utf-8")
                    self.assertFalse(allowed())
            policy.write_text(json.dumps({**valid, "telemetry": 0.25}),
                              encoding="utf-8")
            self.assertTrue(allowed())


    def test_installed_permission_binds_original_owner_request_and_source(self):
        # Patch an isolated controller fixture, never touching Supervisor/NOX.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        required = {"replace_once", "bound_permission_helper", "patch_permission"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in required]
        self.assertEqual({node.name for node in nodes}, required)
        literal = next(node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "PERMISSION_HELPER"
                               for t in node.targets))
        namespace = {"re": re, "PERMISSION_HELPER": ast.literal_eval(literal.value)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        controller = (
            '# NOX_OWNER_ADMISSION_GUARD_V1\n'
            'def _nox_owner_task_admitted(task):\n'
            '    return False\n'
            'def sv_start(name):\n'
            '    if _nox_owner_boost_active() and name in ("nox-train-volta-t866u","nox-train-worm-t811u",\n'
            '            "nox-offload-t850u","nox-downloads-t802u","nox-watch-swap-t845u","nox-agent-architect-t859u","nox-agent-tuner-t858u"):\n'
            '        return False\n'
        )
        request_id, source_sha = "6912345678", "a" * 40
        rendered = namespace["patch_permission"](controller, request_id, source_sha)
        self.assertNotIn("__NOX_OWNER_REQUEST_ID__", rendered)
        self.assertNotIn("__NOX_OWNER_SOURCE_SHA__", rendered)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "state").mkdir()
            policy = root / "state/task_boost_mode.json"
            installed = {"ROOT": root}
            exec(compile(rendered, "<isolated-controller>", "exec"), installed)
            allowed = installed["_nox_owner_training_allowed"]
            valid = {
                "enabled": True, "mode": "TASK_BOOST", "training_allowed": True,
                "training_service": "nox-train-volta-t866u",
                "training_request": request_id, "training_source_sha": source_sha,
            }
            policy.write_text(json.dumps(valid), encoding="utf-8")
            self.assertTrue(allowed())
            for change in ({"training_request": "6912345679"},
                           {"training_request": ""},
                           {"training_request": None},
                           {"training_source_sha": "b" * 40},
                           {"training_source_sha": ""}):
                policy.write_text(json.dumps({**valid, **change}), encoding="utf-8")
                self.assertFalse(allowed())
            for missing in ("training_request", "training_source_sha"):
                policy.write_text(json.dumps({k: v for k, v in valid.items()
                                              if k != missing}), encoding="utf-8")
                self.assertFalse(allowed())
        for bad_request, bad_sha in (("abc", source_sha), ("", source_sha),
                                     (request_id, "A" * 40), (request_id, "bad")):
            with self.assertRaisesRegex(RuntimeError, "HOLD_OWNER_REQUEST_CONTEXT"):
                namespace["patch_permission"](controller, bad_request, bad_sha)


    def test_followup_and_continuation_require_original_policy_owner(self):
        # Isolate source function; no owner entrypoint or trainer process.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "verify_training_policy_owner"]
        self.assertEqual(len(selected), 1)
        scope = {"re": re}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), scope)
        check = scope["verify_training_policy_owner"]
        admission = {"request": "6912345678", "source_sha": "a" * 40}
        policy = {"training_allowed": True, "training_service": "nox-train-volta-t866u",
                  "training_request": admission["request"],
                  "training_source_sha": admission["source_sha"]}
        self.assertTrue(check(policy, admission))
        for changes in ({"training_request": "6912345679"},
                        {"training_request": None},
                        {"training_source_sha": "b" * 40},
                        {"training_source_sha": None}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(RuntimeError, "HOLD_TRAINING_POLICY_OWNER_MISMATCH"):
                    check({**policy, **changes}, admission)
        for missing in ("training_request", "training_source_sha"):
            with self.subTest(missing=missing):
                with self.assertRaisesRegex(RuntimeError, "HOLD_TRAINING_POLICY_OWNER_MISMATCH"):
                    check({k: v for k, v in policy.items() if k != missing}, admission)
        for invalid in ({"request": 6912345678, "source_sha": "a" * 40},
                        {"request": "6912345678", "source_sha": "A" * 40},
                        {"request": "other", "source_sha": "a" * 40}):
            with self.assertRaisesRegex(RuntimeError, "HOLD_TRAINING_POLICY_OWNER_MISMATCH"):
                check(policy, invalid)
        main_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name == "main")
        guarded_calls = [node for node in ast.walk(main_node)
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == "verify_training_policy_owner"]
        self.assertEqual(len(guarded_calls), 2)



    def test_backup_descriptor_binds_exact_original_source_bytes(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "stable_backup_bytes"]
        self.assertEqual(len(selected), 1)
        scope = {"Path": Path, "os": os, "stat": stat,
                 "hashlib": hashlib, "re": re}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), scope)
        stable = scope["stable_backup_bytes"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            owned = root / "original.py"
            foreign = root / "foreign.py"
            owned.write_bytes(b"original verified owner source")
            foreign.write_bytes(b"unrelated source; must never be backed up")
            expected = hashlib.sha256(owned.read_bytes()).hexdigest()
            self.assertEqual(stable(owned, expected), owned.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_PREIMAGE_MISMATCH"):
                stable(owned, "f" * 64)
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_SOURCE_CHANGED"):
                stable(owned, expected, max_bytes=5)
            moved = root / "moved-original.py"
            original_stat = os.stat
            def replace_during_read(path, *args, **kwargs):
                if Path(path) == owned:
                    os.replace(owned, moved)
                    owned.symlink_to(foreign)
                return original_stat(path, *args, **kwargs)
            with mock.patch("os.stat", side_effect=replace_during_read):
                with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_SOURCE_CHANGED"):
                    stable(owned, expected)
            self.assertEqual(moved.read_bytes(), b"original verified owner source")
            self.assertTrue(owned.is_symlink())
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_SOURCE_CHANGED"):
                stable(owned, expected)
        # The production backup closure must pass this verified descriptor
        # snapshot to atomic backup, and install must bind the preimage hash.
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        nested = {node.name: node for node in main.body
                  if isinstance(node, ast.FunctionDef)}
        self.assertIn("stable_backup_bytes(", ast.unparse(nested["backup"]))
        self.assertIn("backup(path, expected[path])", ast.unparse(nested["install"]))



    def test_continuation_wrapper_backup_rejects_foreign_or_rebound_preimage(self):
        """Execute the real continuation backup AST, not a duplicate mock algorithm."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "main")
        matching = [n for n in ast.walk(main)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "atomic" and len(n.args) == 2
                    and ast.unparse(n.args[0]) == "backups / 'first_five_wrapper.sh'"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(ast.unparse(matching[0].args[1]),
                         "stable_backup_bytes(WRAPPER, expected[WRAPPER])")
        backup_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                         and n.name == "stable_backup_bytes")
        scope = {"Path": Path, "os": os, "stat": stat, "re": re, "hashlib": hashlib}
        exec(compile(ast.Module(body=[backup_fn], type_ignores=[]), str(SOURCE), "exec"), scope)
        code = compile(ast.fix_missing_locations(
            ast.Expression(body=copy.deepcopy(matching[0]))), str(SOURCE), "eval")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wrapper = root / "first_five_wrapper.sh"
            foreign = root / "foreign.sh"
            original = b"#!/bin/sh\\necho original\\n"
            wrapper.write_bytes(original)
            foreign.write_bytes(b"#!/bin/sh\\necho foreign\\n")
            writes = []
            class AtomicRecorder:
                def atomic(self, path, data):
                    writes.append((path, data))
            scope.update(helper=AtomicRecorder(), WRAPPER=wrapper, backups=root,
                         expected={wrapper: hashlib.sha256(original).hexdigest()})
            eval(code, scope)
            self.assertEqual(writes, [(root / "first_five_wrapper.sh", original)])
            wrapper.write_bytes(foreign.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_PREIMAGE_MISMATCH"):
                eval(code, scope)
            wrapper.unlink()
            wrapper.symlink_to(foreign)
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_SOURCE_CHANGED"):
                eval(code, scope)
            self.assertEqual(len(writes), 1)

    def test_start_once_waits_for_running_native_identity_not_starting(self):
        # Execute the actual nested start_once: no supervisor, GPU or trainer.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        start_node = next(n for n in main.body
                     if isinstance(n, ast.FunctionDef) and n.name == "start_once")
        def run(states, stop_sequence=None, fast_timeout=False):
            seen, starts, proofs, waits, steps = [], [], [], [], []
            state_iter = iter(states)
            stop_iter = iter(stop_sequence or [])
            def service_state():
                status = next(state_iter, states[-1])
                seen.append(status)
                return {"state": status, "pid": 37}
            def stopping():
                return next(stop_iter, False)
            tick = [0]
            def monotonic():
                tick[0] += 16 if fast_timeout else 0.1
                return tick[0]
            helper = types.SimpleNamespace(
                command=lambda args, timeout: (starts.append((args, timeout)) or (0, "")),
                service_state=service_state,
            )
            namespace = {
                "helper": helper, "global_stop": stopping,
                "SERVICE": "nox-train-volta-t866u",
                "result": {"training_started": False},
                "time": types.SimpleNamespace(monotonic=monotonic,
                                              sleep=lambda interval: waits.append(interval)),
                "prove_training": lambda _: (proofs.append(seen[-1]) or {"pid": 37}),
                "step": lambda kind, data: steps.append(kind),
            }
            exec(compile(ast.Module(body=[start_node], type_ignores=[]),
                         str(SOURCE), "exec"), namespace)
            return namespace["start_once"], namespace, starts, proofs, waits, steps
        start, ctx, starts, proofs, waits, steps = run(
            ["STARTING", "STARTING", "RUNNING"])
        start(5)
        self.assertEqual(len(starts), 1)
        self.assertEqual(proofs, ["RUNNING"])
        self.assertEqual(waits, [0.5, 0.5])
        self.assertEqual(steps, ["single_native_training_started"])
        self.assertTrue(ctx["result"]["training_started"])
        start, ctx, starts, proofs, waits, steps = run(
            ["STARTING"], fast_timeout=True)
        with self.assertRaisesRegex(RuntimeError, "HOLD_SINGLE_TRAINER_START_TIMEOUT"):
            start(5)
        self.assertEqual(len(starts), 1)
        self.assertEqual(proofs, [])
        self.assertFalse(ctx["result"]["training_started"])
        self.assertEqual(steps, [])
        # A STOP asserted during STARTING must refuse the identity receipt.
        start, ctx, starts, proofs, waits, steps = run(
            ["STARTING", "RUNNING"], stop_sequence=[False, False, True])
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            start(5)
        self.assertEqual(len(starts), 1)
        self.assertEqual(proofs, [])
        self.assertEqual(steps, [])

    def test_existing_followup_waits_for_running_and_verifies_identity(self):
        # Do not attach an incomplete STARTING trainer as an accepted running one.
        # Exercise the actual source function without importing its native entrypoint.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "prove_existing_training"]
        self.assertEqual(len(selected), 1)
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "prove_existing_training"]
        self.assertEqual(len(calls), 2)  # followup and continuation
        self.assertIn("identity = prove_existing_training(helper)", ast.unparse(main))

        def scenario(states, stops=(), timeout=False):
            events, proofs, sleeps = [], [], []
            state_iter, stop_iter = iter(states), iter(stops)
            clock = [0.0]
            def service_state():
                state = next(state_iter, states[-1])
                events.append(state)
                return {"state": state} if type(state) is str else state
            def global_stop():
                return next(stop_iter, False)
            def monotonic():
                clock[0] += 16.0 if timeout else 0.1
                return clock[0]
            namespace = {
                "helper": types.SimpleNamespace(service_state=service_state),
                "STOPPED": ("STOPPED", "EXITED", "FATAL"),
                "global_stop": global_stop,
                "time": types.SimpleNamespace(monotonic=monotonic,
                                              sleep=lambda delay: sleeps.append(delay)),
                "prove_training": lambda helper: (
                    proofs.append(events[-1]) or {"pid": 731}),
            }
            exec(compile(ast.Module(body=selected, type_ignores=[]),
                         str(SOURCE), "exec"), namespace)
            return namespace["prove_existing_training"], namespace["helper"], proofs, sleeps

        check, service, proofs, sleeps = scenario(["STARTING", "STARTING", "RUNNING"])
        self.assertEqual(check(service), {"pid": 731})
        self.assertEqual(proofs, ["RUNNING"])
        self.assertEqual(sleeps, [0.5, 0.5])
        check, service, proofs, _ = scenario(["STARTING"], timeout=True)
        with self.assertRaisesRegex(RuntimeError, "HOLD_EXISTING_TRAINER_START_TIMEOUT"):
            check(service)
        self.assertFalse(proofs)
        check, service, proofs, _ = scenario(["STARTING", "STOPPED"])
        with self.assertRaisesRegex(RuntimeError, "HOLD_EXISTING_TRAINER_NOT_RUNNING"):
            check(service)
        self.assertFalse(proofs)
        check, service, proofs, _ = scenario(["STARTING", "RUNNING"],
                                             stops=[False, True])
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            check(service)
        self.assertFalse(proofs)
        check, service, proofs, _ = scenario(["RUNNING"], stops=[True])
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            check(service)
        self.assertFalse(proofs)
        # Transient malformed Supervisor readback must HOLD before accepting
        # a followup, both on the first read and after a STARTING poll.
        malformed = (None, [], {}, {"pid": 37}, {"state": None},
                     {"state": []}, {"state": False},
                     {"state": {"nested": "RUNNING"}})
        for value in malformed:
            for sequence in ([value], ["STARTING", value]):
                with self.subTest(reply=repr(value), after_starting=len(sequence) == 2):
                    check, service, proofs, _ = scenario(sequence)
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_EXISTING_TRAINER_STATUS_READBACK"):
                        check(service)
                    self.assertFalse(proofs)
        check, service, proofs, _ = scenario(["STARTING", "RUNNING"])
        self.assertEqual(check(service), {"pid": 731})
        self.assertEqual(proofs, ["RUNNING"])


    def test_initial_controller_render_and_install_pin_original_preimage(self):
        """Exercise actual controller render/installer AST without native execution."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "main")
        assignments = [n for n in ast.walk(main) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "changed"
                               for t in n.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertIn("stable_backup_bytes(path, expected[path]).decode('utf-8')",
                      ast.unparse(assignments[0].value))
        backups = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "stable_backup_bytes"]
        self.assertEqual(len(backups), 1)
        installer = next(n for n in main.body if isinstance(n, ast.FunctionDef)
                         and n.name == "install")
        self.assertIn("old != expected[path]", ast.unparse(installer))
        self.assertIn("backup(path, expected[path])", ast.unparse(installer))
        scope = {"Path": Path, "os": os, "stat": stat, "hashlib": hashlib, "re": re}
        exec(compile(ast.Module(body=backups, type_ignores=[]),
                     str(SOURCE), "exec"), scope)
        render = compile(ast.fix_missing_locations(
            ast.Expression(body=copy.deepcopy(assignments[0].value))),
            str(SOURCE), "eval")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            control = root / "owner_controller.py"
            foreign = root / "foreign.py"
            original = b"original pinned controller source"
            foreign.write_bytes(b"foreign controller source")
            control.write_bytes(original)
            pin = hashlib.sha256(original).hexdigest()
            scope.update(CONTROLS=[control], expected={control: pin},
                         request="1", source="a" * 40,
                         patch_permission=lambda raw, *_: "patched:" + raw)
            self.assertEqual(eval(render, scope),
                             {control: b"patched:original pinned controller source"})
            control.write_bytes(foreign.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_PREIMAGE_MISMATCH"):
                eval(render, scope)
            control.unlink()
            control.symlink_to(foreign)
            with self.assertRaisesRegex(RuntimeError, "HOLD_BACKUP_SOURCE_CHANGED"):
                eval(render, scope)
            control.unlink()
            control.write_bytes(original)

            backups_seen, installs_seen, steps = [], [], []
            class Recorder:
                def atomic(self, path, data):
                    installs_seen.append((path, data))
                    path.write_bytes(data)
            scope.update(helper=Recorder(),
                         file_sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
                         backup=lambda path, sha: backups_seen.append((path, sha)),
                         step=lambda kind, data: steps.append(kind))
            exec(compile(ast.Module(body=[installer], type_ignores=[]),
                         str(SOURCE), "exec"), scope)
            install = scope["install"]
            control.write_bytes(foreign.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "HOLD_INSTALLED_TRAINING_SOURCE_CHANGED"):
                install(control, b"patched")
            self.assertEqual(backups_seen, [])
            self.assertEqual(installs_seen, [])
            control.write_bytes(original)
            install(control, b"patched")
            self.assertEqual(backups_seen, [(control, pin)])
            self.assertEqual(installs_seen, [(control, b"patched")])
            self.assertEqual(steps, ["source_installed"])
            self.assertEqual(scope["expected"][control],
                             hashlib.sha256(b"patched").hexdigest())


class NativeThreeWorkerCap(unittest.TestCase):
    def test_pinned_three_native_workers_do_not_claim_six_logical_lanes(self):
        """Execute the actual readback AST against fresh native owner fixtures."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "worker_readback"]
        self.assertEqual(len(nodes), 1)
        cap = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "NATIVE_WORKER_CAP"
                       for t in node.targets)]
        self.assertEqual(len(cap), 1)
        self.assertEqual(ast.literal_eval(cap[0].value), 3)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            status = root / "status"
            status.mkdir()
            target = status / "agents_t856u.json"
            # Execute the real protected descriptor reader with the native gate.
            reader = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "read_json"]
            self.assertEqual(len(reader), 1)
            scope = {"Path": Path, "ROOT": root, "NATIVE_WORKER_CAP": 3,
                     "time": __import__("time"), "os": os, "stat": stat,
                     "hashlib": hashlib, "json": json, "math": math, "re": re}
            exec(compile(ast.Module(body=reader + nodes, type_ignores=[]),
                         str(SOURCE), "exec"), scope)
            active = {"state": "RUNNING", "pid": 1234}
            helper = types.SimpleNamespace(service_state=lambda name: active)
            check = scope["worker_readback"]

            def write_workers(rows, n=None):
                target.write_text(json.dumps({"n": len(rows) if n is None else n,
                                              "workers": rows}), encoding="utf-8")
            workers = [{"id": "w1", "current_task": None},
                       {"id": "w2", "current_task": {"id": "job-1"}},
                       {"id": "w3", "current_task": None}]
            write_workers(workers)
            proof = check(helper)
            self.assertEqual(proof["workers"], 3)
            self.assertEqual(proof["worker_ids"], ["w1", "w2", "w3"])
            self.assertEqual(proof["claimed_task_ids"], ["job-1"])
            self.assertAlmostEqual(proof["mtime"], target.stat().st_mtime)
            # The native status file may contain valid JSON with a non-map root.
            # Invalid native proof must HOLD, not leak AttributeError from .get().
            for invalid_root in (None, [], "RUNNING", 3, True):
                with self.subTest(census_root=repr(invalid_root)):
                    target.write_text(json.dumps(invalid_root), encoding="utf-8")
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_NATIVE_WORKER_CAP_READBACK"):
                        check(helper)
            write_workers(workers)
            self.assertEqual(check(helper)["worker_ids"], ["w1", "w2", "w3"])
            # Rebinding/freshening the pathname after the original read must
            # not launder a stale native-worker snapshot into current proof.
            real_reader = scope["read_json"]
            def refresh_path_after_read(path, **kwargs):
                snapshot = real_reader(path, **kwargs)
                os.utime(path, None)
                return snapshot
            scope["read_json"] = refresh_path_after_read
            past = __import__("time").time() - 300
            os.utime(target, (past, past))
            try:
                with self.assertRaisesRegex(RuntimeError, "HOLD_NATIVE_WORKER_CAP_READBACK"):
                    check(helper)
            finally:
                scope["read_json"] = real_reader
            # A clock-skewed or deliberately future-dated census must not
            # be accepted forever just because its mtime exceeds now-90s.
            future = __import__("time").time() + 3600
            os.utime(target, (future, future))
            with self.assertRaisesRegex(RuntimeError, "HOLD_NATIVE_WORKER_CAP_READBACK"):
                check(helper)
            write_workers(workers)
            self.assertEqual(check(helper)["busy_count"], 1)
            for invalid_rows, n in (
                (workers + [{"id": "w4", "current_task": None},
                            {"id": "w5", "current_task": None},
                            {"id": "w6", "current_task": None}], 6),
                (workers[:2], 2),
                ([workers[0], workers[0], workers[2]], 3),
                (workers, True),
            ):
                write_workers(invalid_rows, n)
                with self.assertRaisesRegex(RuntimeError, "HOLD_NATIVE_WORKER_CAP_READBACK"):
                    check(helper)
            # Malformed external identifiers must not leak TypeError/KeyError
            # or be interpreted as a valid 3-worker owner census.
            for invalid_worker in (
                {"id": [], "current_task": None},
                {"id": {"nested": "w1"}, "current_task": None},
                {"id": "   ", "current_task": None},
                {"id": True, "current_task": None},
                {"id": "w1", "current_task": {"id": []}},
                {"id": "w1", "current_task": {"id": {"task": 1}}},
                {"id": "w1", "current_task": {}},
                {"id": "w1", "current_task": {"id": "   "}},
                {"id": "w1", "current_task": "job-1"},
            ):
                with self.subTest(worker=invalid_worker):
                    write_workers([invalid_worker, workers[1], workers[2]])
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_NATIVE_WORKER_CAP_READBACK"):
                        check(helper)
            write_workers(workers)
            with self.assertRaisesRegex(RuntimeError, "HOLD_NATIVE_WORKER_CAP_READBACK"):
                check(helper, fresh_after=__import__("time").time() + 120)
            # Supervisor may return an incomplete or non-object status;
            # never leak KeyError/TypeError or admit an ambiguous owner.
            for malformed_service in (None, [], "RUNNING", {}, {"pid": 1234},
                                      {"state": []}, {"state": {"status": "RUNNING"}}):
                with self.subTest(dispatcher_service=repr(malformed_service)):
                    active = malformed_service
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_DISPATCHER_NOT_RUNNING"):
                        check(helper)
            active = {"state": "RUNNING", "pid": 1234}
            self.assertEqual(check(helper)["dispatcher_pid"], 1234)
            # RUNNING is not enough: only a strictly positive integer PID
            # can attest an actual dispatcher process in native admission.
            for invalid_pid in (None, False, True, 0, -3, "1234", 1.5, [], {}):
                with self.subTest(dispatcher_pid=invalid_pid):
                    active = {"state": "RUNNING", "pid": invalid_pid}
                    with self.assertRaisesRegex(RuntimeError, "HOLD_DISPATCHER_IDENTITY"):
                        check(helper)
            active = {"state": "RUNNING", "pid": 1234}
            self.assertEqual(check(helper)["dispatcher_pid"], 1234)
            active = {"state": "STOPPED", "pid": None}
            with self.assertRaisesRegex(RuntimeError, "HOLD_DISPATCHER_NOT_RUNNING"):
                check(helper)


class NativeDrainStopFence(unittest.TestCase):
    def test_stop_latched_during_worker_drain_blocks_controller_mutation(self):
        """Execute the real main() drain AST: STOP can arrive mid-drain."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        waits = [node for node in ast.walk(main)
                 if isinstance(node, ast.While)
                 and "worker_readback(helper)" in ast.unparse(node.test)]
        self.assertEqual(len(waits), 1)
        drain = waits[0]
        blocks = [node.body for node in ast.walk(main)
                  if isinstance(getattr(node, "body", None), list)
                  and drain in node.body]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        index = block.index(drain)
        self.assertIn("global_stop()", ast.unparse(drain.body[0]))
        self.assertIn("global_stop()", ast.unparse(block[index + 2]))
        self.assertIn("stop_controller", ast.unparse(block[index + 3]))
        selected = ast.fix_missing_locations(ast.Module(
            body=copy.deepcopy(block[index:index + 3]), type_ignores=[]))
        code = compile(selected, str(SOURCE), "exec")

        def attempt(busy_poll_values, stop_values):
            polls, stops, sleeps = iter(busy_poll_values), iter(stop_values), []
            scope = {
                "helper": object(), "deadline": 100,
                "worker_readback": lambda _helper: {"busy_count": next(polls)},
                "global_stop": lambda: next(stops),
                "time": types.SimpleNamespace(monotonic=lambda: 0,
                                               sleep=lambda n: sleeps.append(n)),
            }
            exec(code, scope)
            return sleeps

        # STOP observed during an existing busy worker's drain.
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            attempt([1], [True])
        # STOP asserted just as the last busy worker becomes idle.
        with self.assertRaisesRegex(RuntimeError, "HOLD_GLOBAL_STOP_REMAINS"):
            attempt([1, 0, 0], [False, True])
        # No STOP: original drain is unchanged and reaches controller phase.
        self.assertEqual(attempt([1, 0, 0], [False, False]), [2])



class ControllerRestorationReceiptFence(unittest.TestCase):
    def test_malformed_supervisor_restoration_is_hold_and_unlocks(self):
        """Execute the actual main.finally restoration AST; never call Supervisor."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        finalizer = next(node for node in ast.walk(main)
                         if isinstance(node, ast.Try) and node.finalbody
                         and any("controllers_stopped" in ast.unparse(stmt)
                                 for stmt in node.finalbody))
        restoration = finalizer.finalbody[0]
        self.assertIsInstance(restoration, ast.If)
        self.assertIn("controllers_stopped", ast.unparse(restoration))
        code = compile(ast.fix_missing_locations(ast.Module(
            body=[copy.deepcopy(restoration)], type_ignores=[])), str(SOURCE), "exec")

        def simulate(snapshots, rc=0):
            states, commands, unlocks = iter(snapshots), [], []
            helper = types.SimpleNamespace(
                service_state=lambda name: next(states),
                command=lambda argv, timeout: (commands.append(argv) or rc, ""))
            result = {"state": "BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING",
                      "steps": []}
            scope = {
                "helper": helper, "result": result, "controllers_stopped": ["ctrl-a"],
                "lock_held": True, "success": True, "fd": 71, "re": re,
                "fcntl": types.SimpleNamespace(
                    LOCK_UN="unlock",
                    flock=lambda fd, mode: unlocks.append((fd, mode))),
                "time": types.SimpleNamespace(time=lambda: 123.0),
            }
            exec(code, scope)
            self.assertEqual(unlocks, [(71, "unlock")])
            self.assertFalse(scope["lock_held"])
            return scope, commands

        for malformed in (None, [], {}, {"state": []}, "STOPPED",
                          {"state": "FATAL"}, {"state": True}):
            with self.subTest(snapshot=repr(malformed)):
                state, commands = simulate([malformed])
                self.assertFalse(state["success"])
                self.assertEqual(commands, [])
                self.assertEqual(state["result"]["state"], "HOLD_TRAINING_RESUME")
                self.assertEqual(state["result"]["restore_error"],
                                 "HOLD_CONTROLLER_RESTORE_READBACK")
                self.assertEqual(state["result"]["steps"][-1]["kind"],
                                 "controller_restore_hold")

        state, commands = simulate([{"state": "STOPPED"},
                                    {"state": "RUNNING"}])
        self.assertTrue(state["success"])
        self.assertEqual(commands, [["supervisorctl", "start", "ctrl-a"]])
        self.assertEqual(state["result"]["steps"][-1]["kind"], "controller_restored")

        state, commands = simulate([{"state": "STOPPED"}], rc=1)
        self.assertFalse(state["success"])
        self.assertEqual(state["result"]["restore_error"],
                         "HOLD_CONTROLLER_RESTORE_FAILED")
        self.assertEqual(len(commands), 1)

        state, commands = simulate([{"state": "STOPPED"}, None])
        self.assertFalse(state["success"])
        self.assertEqual(state["result"]["restore_error"],
                         "HOLD_CONTROLLER_RESTORE_READBACK")
        self.assertEqual(len(commands), 1)

        state, commands = simulate([{"state": "RUNNING"}])
        self.assertTrue(state["success"])
        self.assertEqual(commands, [])


class ChatHealthReadbackSchema(unittest.TestCase):
    def test_native_chat_health_shape_fails_closed_without_changing_healthy_200(self):
        """Execute the actual isolated admission; never call real GPU or proxy."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "train_cpu_max.env").write_text(
                "TRAIN_CPU_MAX=64GiB\n", encoding="utf-8")
            verify = load_pinned_verifier(root)["resource_admission"]
            sources = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",
            }
            state = [{"8080": 200}]

            def fake_read_text(path, *args, **kwargs):
                return sources[str(path)]

            helper = types.SimpleNamespace(
                service_state=lambda: {"state": "STOPPED"},
                gpu=lambda: {"gpus": [{"index": 1, "free_mib": 30000}]},
                resource_budget=lambda *args: {"train_cpu_gib": 64},
                health=lambda: state[0],
            )
            with (mock.patch.object(Path, "read_text", autospec=True,
                                    side_effect=fake_read_text),
                  mock.patch("os.sched_getaffinity", return_value={0, 1, 2, 3})):
                self.assertEqual(
                    verify(helper)["budget"]["configured_train_cpu_gib"], 64)
                for malformed in (None, [], "healthy", 200, {"8080": 200.0}):
                    with self.subTest(malformed=repr(malformed)):
                        state[0] = malformed
                        with self.assertRaisesRegex(
                                RuntimeError, "HOLD_CHAT_HEALTH_READBACK"):
                            verify(helper)
                # ConnectionRefusedError is the established native helper
                # convention for offline /health, not a schema error.
                for unhealthy in (
                    {}, {"8080": True}, {"8080": "200"},
                    {"8080": None}, {"8080": []},
                    {"8080": {"status": 200}}, {"8080": float("nan")},
                    {"8080": "ConnectionRefusedError"},
                ):
                    with self.subTest(unhealthy=repr(unhealthy)):
                        state[0] = unhealthy
                        with self.assertRaisesRegex(
                                RuntimeError, "HOLD_CHAT_HEALTH_BEFORE_TRAINING"):
                            verify(helper)
                state[0] = {"8080": 503}
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_CHAT_HEALTH_BEFORE_TRAINING"):
                    verify(helper)
                state[0] = {"8080": 200}
                self.assertEqual(verify(helper)["gpu1"]["index"], 1)


class FinalChatHealthReceiptFence(unittest.TestCase):
    def test_final_proxy_health_schema_is_strict_and_receiptable(self):
        """Execute main's final actual guard without calling native serving."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        guards = [node for node in ast.walk(main)
                  if isinstance(node, ast.If) and len(node.body) == 3
                  and isinstance(node.body[0], ast.Assign)
                  and "chat_health_regression" in ast.unparse(node.body[0])]
        self.assertEqual(len(guards), 1)
        self.assertIn("8080", ast.unparse(guards[0].test))
        code = compile(ast.fix_missing_locations(ast.Module(
            body=[copy.deepcopy(guards[0])], type_ignores=[])), str(SOURCE), "exec")

        for malformed in (None, [], "error", 200, {}, {"8080": True},
                          {"8080": 200.0}, {"8080": "200"},
                          {"8080": float("nan")}, {"8080": 503}):
            with self.subTest(chat_after=repr(malformed)):
                scope = {"result": {"chat_after": malformed,
                                    "state": "CONTINUATION_TARGET_1000_COMPLETED"},
                         "success": True}
                exec(code, scope)
                self.assertFalse(scope["success"])
                self.assertIs(scope["result"]["chat_health_regression"], True)
                self.assertEqual(scope["result"]["state"], "HOLD_TRAINING_RESUME")

        scope = {"result": {"chat_after": {"8080": 200},
                            "state": "CONTINUATION_TARGET_1000_COMPLETED"},
                 "success": True}
        exec(code, scope)
        self.assertTrue(scope["success"])
        self.assertNotIn("chat_health_regression", scope["result"])
        self.assertEqual(scope["result"]["state"], "CONTINUATION_TARGET_1000_COMPLETED")



class ContinuationSupervisorReadbackFence(unittest.TestCase):
    def test_four_continuation_observations_fail_closed_on_malformed_supervisor(self):
        # Execute the reviewed guard AST; no native process, GPU or service.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        guard = next(node for node in tree.body
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "read_training_status")
        scope = {"STOPPED": ("STOPPED", "EXITED", "FATAL")}
        exec(compile(ast.Module(body=[guard], type_ignores=[]),
                     str(SOURCE), "exec"), scope)
        read = scope["read_training_status"]
        for malformed in (
            None, [], "RUNNING", {}, {"state": None},
            {"state": True}, {"state": 1}, {"state": b"RUNNING"},
            {"state": "BACKOFF"}, {"state": "STOPPING"},
            {"state": "UNKNOWN"}, {"state": ["RUNNING"]},
        ):
            with self.subTest(status=repr(malformed)):
                helper = types.SimpleNamespace(service_state=lambda: malformed)
                with self.assertRaisesRegex(RuntimeError, "HOLD_TRAINER_STATUS_READBACK"):
                    read(helper)
        for state in ("RUNNING", "STARTING", "STOPPED", "EXITED", "FATAL"):
            snapshot = {"state": state}
            helper = types.SimpleNamespace(service_state=lambda: snapshot)
            self.assertIs(read(helper), snapshot)

        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        guarded = [node for node in ast.walk(main)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id == "read_training_status"]
        self.assertEqual(len(guarded), 4)
        raw_indexing = [node for node in ast.walk(main)
                        if isinstance(node, ast.Subscript)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr == "service_state"
                        and not node.value.args]
        self.assertEqual(raw_indexing, [])



class FinalReadbackReceiptContinuity(unittest.TestCase):
    def test_one_failed_native_observation_cannot_erase_final_receipt(self):
        # Execute the actual helper AST with simulated transport failures only.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "final_observation_snapshots")
        namespace = {"re": re}
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        snapshot = namespace["final_observation_snapshots"]
        keys = ("service_after", "chat_after", "gpu_after", "progress_after")
        healthy = ({"state": "RUNNING"}, {"8080": 200},
                   {"gpus": []}, {"step": 5})

        def failure():
            raise RuntimeError("HOLD_FINAL_READBACK_OFFLINE")

        def other_failure():
            raise ValueError("temporary transport break")

        for broken in range(len(keys)):
            for failed in (failure, other_failure):
                with self.subTest(field=keys[broken], exception=failed.__name__):
                    getters = [lambda value=value: value for value in healthy]
                    getters[broken] = failed
                    helper = types.SimpleNamespace(
                        service_state=getters[0], health=getters[1],
                        gpu=getters[2], progress=getters[3])
                    observed, errors = snapshot(helper)
                    self.assertEqual(set(observed), set(keys))
                    self.assertEqual(set(errors), {keys[broken]})
                    self.assertIsNone(observed[keys[broken]])
                    for index, key in enumerate(keys):
                        if index != broken:
                            self.assertEqual(observed[key], healthy[index])
                    expected = ("HOLD_FINAL_READBACK_OFFLINE"
                                if failed is failure else "ValueError")
                    self.assertEqual(errors[keys[broken]], expected)

        helper = types.SimpleNamespace(
            service_state=lambda: healthy[0], health=lambda: healthy[1],
            gpu=lambda: healthy[2], progress=lambda: healthy[3])
        self.assertEqual(snapshot(helper), (dict(zip(keys, healthy)), {}))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "main")
        code = ast.unparse(main)
        self.assertIn("final_snapshots, final_errors = final_observation_snapshots(helper)", code)
        self.assertIn("result['final_readback_errors'] = final_errors", code)
        self.assertIn("result['state'] = 'HOLD_TRAINING_RESUME'", code)
        self.assertLess(code.index("final_observation_snapshots(helper)"),
                        code.rindex("save()"))



class LegacyHeavyServiceReadbackFence(unittest.TestCase):
    def test_malformed_legacy_service_snapshot_cannot_authorize_training(self):
        # Exercise actual source gate AST, not a duplicate in the test.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "ensure_legacy_heavy_services_stopped")
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        code = ast.unparse(main)
        self.assertIn("ensure_legacy_heavy_services_stopped(helper)", code)
        self.assertNotIn("helper.service_state(name)['state']", code)
        scope = {"STOPPED": ("STOPPED", "EXITED", "FATAL")}
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     str(SOURCE), "exec"), scope)
        check = scope["ensure_legacy_heavy_services_stopped"]
        for malformed in (None, [], "STOPPED", {}, {"state": None},
                          {"state": True}, {"state": 0}, {"state": []},
                          {"state": {"value": "STOPPED"}}):
            with self.subTest(malformed=repr(malformed)):
                helper = types.SimpleNamespace(
                    HEAVY_SERVICES=("legacy-a",),
                    service_state=lambda name, value=malformed: value)
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_LEGACY_HEAVY_STATUS_READBACK"):
                    check(helper)
        for state in ("RUNNING", "STARTING", "BACKOFF"):
            with self.subTest(active=state):
                helper = types.SimpleNamespace(
                    HEAVY_SERVICES=("legacy-a",),
                    service_state=lambda name, state=state: {"state": state})
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_LEGACY_HEAVY_SERVICE_REACTIVATED"):
                    check(helper)
        for states in (("STOPPED",), ("EXITED", "FATAL"),
                       ("STOPPED", "EXITED", "FATAL")):
            calls = []
            names = tuple("legacy-" + str(i) for i in range(len(states)))
            snapshots = dict(zip(names, states))
            def read(name):
                calls.append(name)
                return {"state": snapshots[name]}
            helper = types.SimpleNamespace(
                HEAVY_SERVICES=names, service_state=read)
            self.assertIsNone(check(helper))
            self.assertEqual(tuple(calls), names)
        # A later healthy service cannot mask one malformed earlier response.
        calls = []
        def read(name):
            calls.append(name)
            return None if name == "legacy-a" else {"state": "STOPPED"}
        helper = types.SimpleNamespace(
            HEAVY_SERVICES=("legacy-a", "legacy-b"), service_state=read)
        with self.assertRaisesRegex(
                RuntimeError, "HOLD_LEGACY_HEAVY_STATUS_READBACK"):
            check(helper)
        self.assertEqual(calls, ["legacy-a"])



class ExistingTrainerSupervisorStateEnumFence(unittest.TestCase):
    def test_attached_trainer_readback_rejects_unknown_supervisor_states(self):
        """Execute exact nested source read_state; no GPU, I/O or process mutation."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "prove_existing_training")
        scope = {
            "STOPPED": ("STOPPED", "EXITED", "FATAL"),
            "global_stop": lambda: False,
            "time": types.SimpleNamespace(monotonic=lambda: 0.0,
                                          sleep=lambda _seconds: None),
            "prove_training": lambda _helper: {"native_identity": "verified"},
        }
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[copy.deepcopy(fn)], type_ignores=[])), str(SOURCE), "exec"),
             scope)
        attached = scope["prove_existing_training"]
        for malformed in (
            None, [], "RUNNING", {}, {"state": None}, {"state": True},
            {"state": 1}, {"state": []}, {"state": b"RUNNING"},
            {"state": "BACKOFF"}, {"state": "STOPPING"},
            {"state": "UNKNOWN"}, {"state": "RUNNING "},
        ):
            with self.subTest(snapshot=repr(malformed)):
                helper = types.SimpleNamespace(service_state=lambda value=malformed: value)
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_EXISTING_TRAINER_STATUS_READBACK"):
                    attached(helper)

        for terminal in ("STOPPED", "EXITED", "FATAL"):
            helper = types.SimpleNamespace(service_state=lambda s=terminal: {"state": s})
            with self.assertRaisesRegex(
                    RuntimeError, "HOLD_EXISTING_TRAINER_NOT_RUNNING"):
                attached(helper)

        helper = types.SimpleNamespace(service_state=lambda: {"state": "RUNNING"})
        self.assertEqual(attached(helper), {"native_identity": "verified"})
        observations = iter(("STARTING", "RUNNING"))
        helper = types.SimpleNamespace(
            service_state=lambda: {"state": next(observations)})
        self.assertEqual(attached(helper), {"native_identity": "verified"})



class NewTrainerSupervisorStateEnumFence(unittest.TestCase):
    def test_new_start_state_enum_is_fail_closed_before_identity(self):
        """Execute actual nested read_start_status without Supervisor or training."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        matches = [node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "read_start_status"]
        self.assertEqual(len(matches), 1)
        code = compile(ast.Module(body=[copy.deepcopy(matches[0])],
                                  type_ignores=[]), str(SOURCE), "exec")
        for malformed in (
            None, [], "RUNNING", {}, {"state": None}, {"state": True},
            {"state": 1}, {"state": []}, {"state": b"RUNNING"},
            {"state": "BACKOFF"}, {"state": "STOPPING"},
            {"state": "UNKNOWN"}, {"state": "RUNNING "},
            {"state": " starting"}, {"state": "FATAL "},
        ):
            with self.subTest(snapshot=repr(malformed)):
                scope = {"helper": types.SimpleNamespace(
                    service_state=lambda value=malformed: value)}
                exec(code, scope)
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_NEW_TRAINER_STATUS_READBACK"):
                    scope["read_start_status"]()
        for state in ("STARTING", "RUNNING", "STOPPED", "EXITED", "FATAL"):
            with self.subTest(state=state):
                snapshot = {"state": state, "pid": 123}
                scope = {"helper": types.SimpleNamespace(
                    service_state=lambda value=snapshot: value)}
                exec(code, scope)
                self.assertEqual(scope["read_start_status"](), snapshot)



class FinalWorkerCensusSuccessFence(unittest.TestCase):
    def test_failed_final_worker_census_cannot_emit_success_receipt(self):
        """Execute real main() final census Try AST without native side effects."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        census_tries = [node for node in ast.walk(main)
                        if isinstance(node, ast.Try)
                        and any("native_workers_readback_error" in ast.unparse(handler)
                                for handler in node.handlers)]
        self.assertEqual(len(census_tries), 1)
        isolated = compile(ast.fix_missing_locations(ast.Module(
            body=[copy.deepcopy(census_tries[0])], type_ignores=[])),
            str(SOURCE), "exec")

        def hold_failure(_helper):
            raise RuntimeError("HOLD_NATIVE_WORKER_CAP_READBACK")

        def transport_failure(_helper):
            raise ValueError("temporary transport exception")

        for readback, expected in (
                (hold_failure, "HOLD_NATIVE_WORKER_CAP_READBACK"),
                (transport_failure, "ValueError")):
            with self.subTest(error=expected):
                scope = {"result": {"state": "CONTINUATION_TARGET_1000_COMPLETED"},
                         "success": True, "worker_readback": readback,
                         "helper": object()}
                exec(isolated, scope)
                self.assertFalse(scope["success"])
                self.assertEqual(scope["result"]["state"], "HOLD_TRAINING_RESUME")
                self.assertEqual(scope["result"]["native_workers_readback_error"], expected)
                self.assertNotIn("native_workers_after", scope["result"])

        healthy = {"workers": 3, "dispatcher_pid": 444}
        scope = {"result": {"state": "CONTINUATION_TARGET_1000_COMPLETED"},
                 "success": True, "worker_readback": lambda _: healthy,
                 "helper": object()}
        exec(isolated, scope)
        self.assertTrue(scope["success"])
        self.assertEqual(scope["result"]["state"], "CONTINUATION_TARGET_1000_COMPLETED")
        self.assertEqual(scope["result"]["native_workers_after"], healthy)
        self.assertNotIn("native_workers_readback_error", scope["result"])



class BoostInstalledReceiptDuplicateFence(unittest.TestCase):
    def test_ambiguous_native_install_evidence_never_admits_training(self):
        """Run real boost_pins() AST without Supervisor, trainer or GPU."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        fun = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "boost_pins")
        pinned = {Path("/root/nox/scripts/owner-a.py"): "a" * 64,
                  Path("/root/nox/scripts/owner-b.py"): "b" * 64}
        scope = {"BOOST_PINS": pinned, "BOOST_REQUEST": "6903121842",
                 "BOOST_SOURCE": "3b964f6c9861ca89437aa158b912dc9686e99cb6"}
        exec(compile(ast.Module(body=[fun], type_ignores=[]), str(SOURCE), "exec"), scope)
        verify = scope["boost_pins"]
        good = {
            "schema": "NOX_OWNER_OPTIMIZE_HYBRID_V1",
            "request": scope["BOOST_REQUEST"],
            "source_sha": scope["BOOST_SOURCE"],
            "state": "TASK_BOOST_SIX_NATIVE_WORKERS_ACTIVE_TRAINING_PAUSED",
            "hold_retained": True, "training_started": False,
            "steps": [
                {"kind": "source_installed", "data": {"path": str(path), "after": sha}}
                for path, sha in pinned.items()
            ],
        }
        self.assertEqual(verify(copy.deepcopy(good)), pinned)
        # Native evidence readers can return a malformed JSON root. Such a
        # receipt must be a named HOLD, not an uncaught AttributeError.
        for malformed_root in (None, [], ["spoof"], "spoof", False, 0, 200.0):
            with self.subTest(root=repr(malformed_root)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_VERIFIED_NATIVE_BOOST_REQUIRED"):
                    verify(malformed_root)
        # Both directions of the duplicate matter: last-write-wins is unsafe.
        a = str(next(iter(pinned)))
        contradicted = {"kind": "source_installed",
                        "data": {"path": a, "after": "0" * 64}}
        for extra in (
            [contradicted, *good["steps"]],
            [*good["steps"], contradicted],
            [good["steps"][0], *good["steps"]],
        ):
            with self.subTest(extra=repr(extra)):
                receipt = copy.deepcopy(good)
                receipt["steps"] = extra
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_BOOST_INSTALLED_RECEIPT_MISMATCH"):
                    verify(receipt)
        for steps in (None, {}, "installed", [None], [["not-a-row"]],
                      [{"kind": "source_installed"}],
                      [{"kind": "source_installed", "data": []}],
                      [{"kind": "source_installed", "data": {"path": a}}],
                      [{"kind": "source_installed",
                        "data": {"path": a, "after": True}}]):
            with self.subTest(malformed=repr(steps)):
                receipt = copy.deepcopy(good)
                receipt["steps"] = steps
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_BOOST_INSTALLED_RECEIPT_MISMATCH"):
                    verify(receipt)


class DispatcherUpgradeReceiptShapeFence(unittest.TestCase):
    def test_malformed_upgrade_evidence_cannot_crash_or_authorize(self):
        """Run real dispatcher_upgrade_pins AST, with no services/weights/GPU."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "dispatcher_upgrade_pins")
        root = Path("/root/nox")
        dispatcher = root / "scripts/nox_dispatcher_t855u.py"
        namespace = {
            "ROOT": root, "re": re,
            "BOOST_PINS": {dispatcher: "a" * 64},
            "UPGRADE_SOURCE_PINS": {"mentor": "b" * 64},
            "DISPATCHER_UPGRADE_REQUEST": "1234",
            "DISPATCHER_UPGRADE_SOURCE": "c" * 40,
            "DISPATCHER_UPGRADE_SHA": "d" * 64,
            "UPGRADE_PINS": {dispatcher: "d" * 64},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        verifier = namespace["dispatcher_upgrade_pins"]
        request = namespace["DISPATCHER_UPGRADE_REQUEST"]
        parent = "owner.autonomy.audit." + request
        child_ids = ["owner.audit." + str(i) for i in range(6)]
        task_ids = [parent, *child_ids]
        plan = {
            "verified": True, "parent_status": "done",
            "scope": "BOUNDED_COMPONENT_AUDIT", "unique_claims": 7,
            "training_optimizer_update_proven": False,
            "children": [{"id": item, "status": "done"} for item in child_ids],
            "proofs": [{"id": item, "receipt_sha256": "e" * 64}
                       for item in task_ids],
            "owner_reports": [{"task_id": item, "kind": "task_verified",
                               "claim": format(i, "024x")}
                              for i, item in enumerate(task_ids)],
        }
        good = {
            "schema": "NOX_OWNER_DISPATCHER_UPGRADE_V1",
            "request": request, "source_sha": namespace["DISPATCHER_UPGRADE_SOURCE"],
            "state": "SIX_WORKER_LIFECYCLE_MEDIA_PLANS_REPORTS_VERIFIED",
            "dispatcher_before": "a" * 64, "dispatcher_after": "d" * 64,
            "source_pins": namespace["UPGRADE_SOURCE_PINS"],
            "rollback": False, "training_started": False,
            "training_hold_sha256": "f" * 64,
            "workers": {"ids": ["worker-" + str(i) for i in range(6)]},
            "native_plan": plan,
        }
        self.assertEqual(verifier(copy.deepcopy(good)),
                         namespace["UPGRADE_PINS"])
        cases = [
            (None, "HOLD_VERIFIED_DISPATCHER_UPGRADE_REQUIRED"),
            ([], "HOLD_VERIFIED_DISPATCHER_UPGRADE_REQUIRED"),
            ({**good, "workers": ["spurious-worker"]},
             "HOLD_DISPATCHER_UPGRADE_SIX_WORKERS_REQUIRED"),
            ({**good, "workers": {"ids": True}},
             "HOLD_DISPATCHER_UPGRADE_SIX_WORKERS_REQUIRED"),
            ({**good, "native_plan": ["unexpected"]},
             "HOLD_DISPATCHER_UPGRADE_NATIVE_PLAN_REQUIRED"),
            ({**good, "native_plan": {**plan,
                                    "children": [*plan["children"], None]}},
             "HOLD_DISPATCHER_UPGRADE_NATIVE_PLAN_REQUIRED"),
            ({**good, "native_plan": {**plan, "proofs": 2}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
            ({**good, "native_plan": {**plan, "owner_reports": True}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
            # Malformed JSON ID arrays/objects used to raise raw TypeError
            # at set comprehensions, bypassing the named owner HOLD.
            ({**good, "native_plan": {**plan, "proofs": [
                {**plan["proofs"][0], "id": ["not-hashable"]},
                *plan["proofs"][1:]]}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
            ({**good, "native_plan": {**plan, "proofs": [
                {**plan["proofs"][0], "id": {"foreign": True}},
                *plan["proofs"][1:]]}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
            ({**good, "native_plan": {**plan, "owner_reports": [
                {**plan["owner_reports"][0], "task_id": ["not-hashable"]},
                *plan["owner_reports"][1:]]}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
            ({**good, "native_plan": {**plan, "owner_reports": [
                {**plan["owner_reports"][0], "task_id": {"foreign": True}},
                *plan["owner_reports"][1:]]}},
             "HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED"),
        ]
        for receipt, reason in cases:
            with self.subTest(receipt=repr(receipt)[:120]):
                with self.assertRaisesRegex(RuntimeError, reason):
                    verifier(copy.deepcopy(receipt))



class S03ContentReindexNestedShapeFence(unittest.TestCase):
    def test_malformed_reindex_receipt_maps_hold_without_crashing(self):
        """Execute real source proof AST only; no S03, GPU or native service."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "s03_content_reindex_proof")
        scope = {"S03_GATEWAY_SHA": "a" * 64,
                 "S03_PREPARE_REQUEST": "10001",
                 "S03_PREPARE_RECEIPT_SHA": "b" * 64,
                 "S03_MODEL_CONTENT_SHA": "c" * 64,
                 "S03_MODEL_IDENTITY": "pinned-bge-identity"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
        check = scope["s03_content_reindex_proof"]
        content = {"request": "10002", "source_sha": "d" * 40,
                   "receipt_sha256": "e" * 64,
                   "current_embeddings": 514, "indexed_in_action": 0}
        chain = {"training_hold_sha256": "f" * 64}
        proc = {"pid": 202, "starttime": 333}
        valid = {
            "schema": "NOX_OWNER_S03_CONTENT_REINDEX_V1",
            "request": content["request"], "source_sha": content["source_sha"],
            "state": "CONTENT_IDENTITY_AND_REEMBEDDED_INDEX_VERIFIED",
            "gateway_sha256": scope["S03_GATEWAY_SHA"],
            "prepare_request": scope["S03_PREPARE_REQUEST"],
            "prepare_source_sha": "2a09e5975e0bfbd84e22bbaea1c0347a9b41ec63",
            "prepare_receipt_sha256": scope["S03_PREPARE_RECEIPT_SHA"],
            "content_identity": {"content_sha256": scope["S03_MODEL_CONTENT_SHA"],
                                 "identity": scope["S03_MODEL_IDENTITY"],
                                 "dimensions": 1024, "full_file_hash_verified": True},
            "status": {"model_identity": scope["S03_MODEL_IDENTITY"],
                       "stale_embeddings": 0, "current_embeddings": 514,
                       "original_history_records_preserved": 1014},
            "before_index": {"legacy_identity_vectors": 0},
            "indexed_in_action": 0, "legacy_vectors_remaining": 0,
            "legacy_vectors_relabelled": False,
            "historical_model_content_sha_known": False,
            "canonical_originals_preserved": True,
            "sources_and_flags_unchanged": True,
            "training_hold_sha256": chain["training_hold_sha256"],
            "training_pause_sha256": chain["training_hold_sha256"],
            "private_text_exported": False, "training_examples_accepted": 0,
            "services_restarted": [], "live_sources_changed": False,
            "bge_process_before": proc, "bge_process_after": dict(proc),
            "synthetic_retrieval_acceptance":
                {"state": "SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED"},
            "public_recall": {"state": "SEMANTIC_LEXICAL_BOUNDED_PINS",
                              "methods": {"semantic": 1, "hybrid": 0, "pin": 0}},
        }
        verified = check(copy.deepcopy(valid), content, chain)
        self.assertEqual(verified["receipt_sha256"], content["receipt_sha256"])
        self.assertEqual(verified["current_embeddings"], 514)

        # R33: Python False == 0 is not proof of a measured zero counter.
        # Reject booleans in signed S03 reindex/holdout admission evidence.
        for field_path in (("status", "stale_embeddings"),
                           ("indexed_in_action",),
                           ("legacy_vectors_remaining",),
                           ("training_examples_accepted",)):
            with self.subTest(counter=field_path):
                candidate = copy.deepcopy(valid)
                target = candidate
                for key in field_path[:-1]:
                    target = target[key]
                target[field_path[-1]] = False
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_S03_CONTENT_REINDEX_CHAIN_REQUIRED$"):
                    check(candidate, content, chain)

        for root in (None, [], "not-a-receipt"):
            with self.subTest(root=repr(root)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_S03_CONTENT_REINDEX_CHAIN_REQUIRED"):
                    check(root, content, chain)
        for field in ("content_identity", "status", "before_index",
                      "bge_process_before", "public_recall",
                      "synthetic_retrieval_acceptance"):
            for malformed in ([], ["crafted"], True, "not-a-map"):
                with self.subTest(field=field, malformed=repr(malformed)):
                    candidate = copy.deepcopy(valid)
                    candidate[field] = malformed
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_S03_CONTENT_REINDEX_CHAIN_REQUIRED"):
                        check(candidate, content, chain)
        for malformed in ([], ["crafted"], True, "not-a-map"):
            candidate = copy.deepcopy(valid)
            candidate["public_recall"]["methods"] = malformed
            with self.subTest(methods=repr(malformed)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_S03_CONTENT_REINDEX_CHAIN_REQUIRED"):
                    check(candidate, content, chain)


    def test_s03_activation_nested_receipt_shape_fence(self):
        # Extract the real source without entering training, GPU or production.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(item for item in tree.body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == "s03_activation_pins")
        root = Path("/root/nox")
        lifecycle = root / "config/owner_task_lifecycle.json"
        scope = {
            "ROOT": root, "re": re,
            "S03_ACTIVATION_REQUEST": "10001",
            "S03_ACTIVATION_SOURCE": "a" * 40,
            "S03_PREPARE_REQUEST": "10002",
            "S03_PREPARE_RECEIPT_SHA": "b" * 64,
            "S03_SOURCE_PINS": {"owner_s03_gateway": "c" * 64},
            "S03_DISPATCHER_SHA": "d" * 64,
            "S03_AFTER_SHA": "c" * 64,
            "S03_GATEWAY_SHA": "a" * 64,
            "S03_MODEL_CONTENT_SHA": "b" * 64,
            "S03_MODEL_IDENTITY": "test-pinned-model",
            "S03_PINS": {lifecycle: "f" * 64},
            "UPGRADE_PINS": {lifecycle: "e" * 64},
            "S03_BEFORE_SHA": "e" * 64,
            "S03_PREPARE_GATEWAY_SHA": "d" * 64,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     str(SOURCE), "exec"), scope)
        check = scope["s03_activation_pins"]
        chain = {"training_hold_sha256": "e" * 64}
        process = {"pid": 202, "starttime": "700"}
        valid = {
            "schema": "NOX_OWNER_S03_ACTIVATION_V1",
            "request": scope["S03_ACTIVATION_REQUEST"],
            "source_sha": scope["S03_ACTIVATION_SOURCE"],
            "state": "LIVE_SHARED_SEMANTIC_MEMORY_AND_NATIVE_INDEX_VERIFIED",
            "prepare_request": scope["S03_PREPARE_REQUEST"],
            "prepare_receipt_sha256": scope["S03_PREPARE_RECEIPT_SHA"],
            "source_pins": scope["S03_SOURCE_PINS"],
            "dispatcher_after_sha256": scope["S03_DISPATCHER_SHA"],
            "s03_after_sha256": scope["S03_AFTER_SHA"],
            "lifecycle_config_sha256": scope["S03_PINS"][lifecycle],
            "training_hold_sha256": chain["training_hold_sha256"],
            "rollback": False, "training_started": False,
            "llama_restarted": False, "private_text_exported": False,
            "weights_deleted": 0, "memory_records_deleted": 0,
            "content_reindex": {
                "schema": "NOX_OWNER_S03_CONTENT_REINDEX_V1",
                "request": scope["S03_ACTIVATION_REQUEST"],
                "source_sha": scope["S03_ACTIVATION_SOURCE"],
                "state": "CONTENT_IDENTITY_AND_REEMBEDDED_INDEX_VERIFIED",
                "gateway_sha256": scope["S03_GATEWAY_SHA"],
                "model_identity": scope["S03_MODEL_IDENTITY"],
                "model_content_sha256": scope["S03_MODEL_CONTENT_SHA"],
                "receipt_sha256": "f" * 64,
                "current_embeddings": 514, "indexed_in_action": 0,
                "stale_embeddings": 0, "legacy_vectors_relabelled": False,
            },
            "workers": {"configured": 6, "observed": 6,
                        "unique_active_claims": 3},
            "model_process_before": process,
            "model_process_after": dict(process),
            "health_after": {"8080": 200, "8081": 200, "8082": 200},
            "native_index_proof": {
                "kind": "bounded_native_s03_index",
                "scope": "BOUNDED_S03_VECTOR_INDEX",
                "source_sha256": scope["S03_GATEWAY_SHA"],
                "receipt_sha256": "f" * 64, "indexed": 0,
                "stale_remaining": 0, "training_examples_accepted": 0,
            },
            "steps": [
                {"kind": "s03_live_proxy_recall",
                 "data": {"state": "SEMANTIC_LEXICAL_BOUNDED_PINS",
                          "private_text_exported": False,
                          "methods": {"semantic": 1, "hybrid": 0, "pin": 0}}},
                {"kind": "s03_lifecycle_recall",
                 "data": {"retrieval_kind": "SEMANTIC_LEXICAL_BOUNDED_PINS",
                          "gateway_source_sha256": scope["S03_GATEWAY_SHA"],
                          "source_sha256": scope["S03_AFTER_SHA"],
                          "content_exported": False}},
            ],
            "installed_sources": [
                {"name": lifecycle.name, "before": "e" * 64,
                 "after": scope["S03_PINS"][lifecycle]},
                {"name": "owner_senior_gateway.json",
                 "before": "e" * 64, "after": "f" * 64},
            ],
        }
        healthy = check(copy.deepcopy(valid), chain)
        self.assertEqual(healthy[lifecycle], scope["S03_PINS"][lifecycle])
        self.assertEqual(len(healthy), 2)
        # R33: false is a JSON boolean, not an observed zero stale-vector count.
        candidate = copy.deepcopy(valid)
        candidate["content_reindex"]["stale_embeddings"] = False
        with self.assertRaisesRegex(
                RuntimeError, "^HOLD_S03_VERIFIED_CONTENT_REINDEX_REQUIRED$"):
            check(candidate, chain)

        # A later valid S03 event must not launder an earlier failed event.
        # Repeated identical proof is ambiguous as well. Unrelated periodic
        # progress events are permitted to repeat.
        for index, kind in enumerate(
                ("s03_live_proxy_recall", "s03_lifecycle_recall")):
            for duplicate_data in ({"state": "FAILED"},
                                   copy.deepcopy(valid["steps"][index]["data"])):
                candidate = copy.deepcopy(valid)
                candidate["steps"].insert(index, {
                    "kind": kind, "data": duplicate_data,
                })
                with self.subTest(kind=kind, duplicate=duplicate_data):
                    with self.assertRaisesRegex(
                            RuntimeError,
                            "^HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED$"):
                        check(candidate, chain)
        repeated_unrelated = copy.deepcopy(valid)
        repeated_unrelated["steps"].extend([
            {"kind": "progress", "data": {"step": 1}},
            {"kind": "progress", "data": {"step": 2}},
        ])
        self.assertEqual(check(repeated_unrelated, chain)[lifecycle],
                         scope["S03_PINS"][lifecycle])

        with self.assertRaisesRegex(
                RuntimeError, "HOLD_VERIFIED_S03_ACTIVATION_REQUIRED"):
            check(copy.deepcopy(valid), ["not-chain"])
        # Every malformed receipt should return a named HOLD, not a Python
        # AttributeError, TypeError or a false admission.
        bad_fields = {
            "content_reindex": "HOLD_S03_VERIFIED_CONTENT_REINDEX_REQUIRED",
            "workers": "HOLD_S03_NATIVE_SIX_WORKERS_REQUIRED",
            "health_after": "HOLD_S03_LIVE_CHAT_PROOF_REQUIRED",
            "native_index_proof": "HOLD_S03_NATIVE_INDEX_PROOF_REQUIRED",
            "steps": "HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED",
        }
        for field, reason in bad_fields.items():
            for malformed in ([], ["crafted"], True, "not-a-map"):
                with self.subTest(field=field, value=repr(malformed)):
                    candidate = copy.deepcopy(valid)
                    candidate[field] = malformed
                    with self.assertRaisesRegex(RuntimeError, reason):
                        check(candidate, chain)
        candidate = copy.deepcopy(valid)
        candidate["steps"] = ["not-a-row"]
        with self.assertRaisesRegex(
                RuntimeError, "HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED"):
            check(candidate, chain)
        for idx in (0, 1):
            for malformed in ([], ["crafted"], True, "not-a-map"):
                with self.subTest(step=idx, value=repr(malformed)):
                    candidate = copy.deepcopy(valid)
                    candidate["steps"][idx]["data"] = malformed
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED"):
                        check(candidate, chain)
        for malformed in ([], ["crafted"], True, "not-a-map"):
            candidate = copy.deepcopy(valid)
            candidate["steps"][0]["data"]["methods"] = malformed
            with self.assertRaisesRegex(
                    RuntimeError, "HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED"):
                check(candidate, chain)
        for malformed in (True, 200.0):
            candidate = copy.deepcopy(valid)
            candidate["health_after"]["8080"] = malformed
            with self.assertRaisesRegex(
                    RuntimeError, "HOLD_S03_LIVE_CHAT_PROOF_REQUIRED"):
                check(candidate, chain)
        candidate = copy.deepcopy(valid)
        candidate["installed_sources"][0]["name"] = []
        with self.assertRaisesRegex(
                RuntimeError, "HOLD_S03_INSTALLED_SOURCE_SET"):
            check(candidate, chain)


    def test_media_acceptance_nested_proof_shape_is_fail_closed(self):
        # Source-isolated actual verifier AST: no production, GPU, media or training.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "media_acceptance_proof")
        root = Path("/root/nox")
        scope = {
            "Path": Path, "re": re, "math": math, "ROOT": root,
            "MEDIA_ACCEPTANCE_REQUEST": "10001",
            "MEDIA_ACCEPTANCE_SOURCE": "a" * 40,
            "STOPPED": ("STOPPED", "EXITED", "FATAL"),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE),
                     "exec"), scope)
        check = scope["media_acceptance_proof"]
        chain = {"training_hold_sha256": "e" * 64}
        base = {
            "schema": "NOX_OWNER_MEDIA_ACCEPTANCE_V1",
            "request": "10001", "source": "a" * 40,
            "state": "GENERATED_DECODED_AND_GPU_RELEASED",
            "pixels_exported": False,
            "release": {
                "forge_lease_reacquired": True, "forge_lease_released": True,
                "original_flags_preserved": True, "training_started": False,
                "hold_sha256": chain["training_hold_sha256"],
                "pause_sha256": chain["training_hold_sha256"],
                "trainer": {"state": "STOPPED", "pid": None},
                "gpu1": {"free_mib": 32000},
            },
            "artifacts": [],
        }
        for kind, job_id in (("image", "a" * 32), ("video", "b" * 32)):
            image = kind == "image"
            suffix = ".png" if image else ".webm"
            decode = {
                "max_channel_range": 4.0,
                "width": 512 if image else 256,
                "height": 512 if image else 256,
                "frames": 1 if image else 9,
                "codec": "png" if image else "vp9",
            }
            if image:
                decode["max_channel_variance"] = 1.0
            else:
                decode.update(decoded_fps=8.0, timestamp_span_seconds=1.0,
                              max_frame_interval_error_seconds=0.001,
                              distinct_decoded_frames=3,
                              timestamps_strictly_increasing=True)
            base["artifacts"].append({
                "kind": kind, "job_id": job_id,
                "path": str(root / "media/outputs/nox" / job_id /
                            ("sample" + suffix)),
                "url": "/api/ui/media/jobs/" + job_id + "/outputs/0",
                "media_type": "image/png" if image else "video/webm",
                "decode_verified": True, "authenticated_http_verified": True,
                "pixels_exported": False,
                "scope": "GENERATED_FILE_DECODE_AND_AUTHENTICATED_DELIVERY",
                "bytes": 100, "sha256": "1" * 64, "decode": decode,
            })
        self.assertEqual([x["kind"] for x in check(copy.deepcopy(base), chain)],
                         ["image", "video"])

        for invalid in (None, [], ["spoof"], True, "not-chain"):
            with self.subTest(chain=repr(invalid)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_MEDIA_ACCEPTANCE_GPU_AND_TRAINER_RELEASE"):
                    check(copy.deepcopy(base), invalid)
        for field in ("release", "trainer", "gpu1"):
            for bad in ([], ["spoof"], True, "non-map"):
                with self.subTest(field=field, value=repr(bad)):
                    row = copy.deepcopy(base)
                    if field == "release":
                        row["release"] = bad
                    else:
                        row["release"][field] = bad
                    with self.assertRaisesRegex(
                            RuntimeError, "HOLD_MEDIA_ACCEPTANCE_GPU_AND_TRAINER_RELEASE"):
                        check(row, chain)
        for bad in ([], ["spoof"], True, {"malformed": 1}):
            row = copy.deepcopy(base)
            row["artifacts"][0]["kind"] = bad
            with self.subTest(kind=repr(bad)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_MEDIA_ACCEPTANCE_TWO_DECODED_OUTPUTS"):
                    check(row, chain)
        for bad in ([], ["spoof"], True, {"malformed": 1}):
            row = copy.deepcopy(base)
            row["artifacts"][0]["decode"] = bad
            with self.subTest(decode=repr(bad)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_MEDIA_ACCEPTANCE_FINITE_DECODE"):
                    check(row, chain)
        for bad in ([], ["spoof"], True, {"malformed": 1}):
            row = copy.deepcopy(base)
            row["artifacts"][0]["path"] = bad
            with self.subTest(path=repr(bad)):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_MEDIA_ACCEPTANCE_ARTIFACT_PROOF"):
                    check(row, chain)



    def test_followup_pointer_sources_fail_closed_on_json_shapes(self):
        # Run exactly the real helper extracted from the owner's source AST.
        # This never starts native training or reads/writes server state.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "verify_followup_pointer_sources")
        namespace = {"re": re, "BOOST_REQUEST": "123456"}
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     str(SOURCE), "exec"), namespace)
        check = namespace["verify_followup_pointer_sources"]
        stable = Path("/root/nox/scripts/stable.py")
        wrapper = Path("/root/nox/scripts/owner_wrapper.sh")
        expected = {stable: "a" * 64, wrapper: "b" * 64}
        sources = {str(stable): "a" * 64, str(wrapper): "c" * 64}
        good = {
            "schema": "NOX_OWNER_TRAINING_ADMISSION_V1",
            "boost_request": "123456",
            "request": "123457",
            "source_sha": "f" * 40,
            "sources": sources,
        }
        self.assertEqual(check(copy.deepcopy(good), expected, {wrapper}),
                         sources)
        # Even a request converted via str() is not a safe pathname segment.
        for malformed in (None, [], "broken", True, 7, 3.5):
            with self.subTest(root=repr(malformed)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_ADMISSION$"):
                    check(malformed, expected, {wrapper})
        for field, malformed_values in {
            "request": (None, True, 123457, [], {}, " 123457", ""),
            "source_sha": (None, True, 11, [], {}, "a" * 39, "A" * 40),
        }.items():
            for invalid in malformed_values:
                with self.subTest(field=field, bad=repr(invalid)):
                    changed = copy.deepcopy(good)
                    changed[field] = invalid
                    with self.assertRaisesRegex(
                            RuntimeError, "^HOLD_PREVIOUS_TRAINING_ADMISSION$"):
                        check(changed, expected, {wrapper})
        for invalid in (None, [], [str(stable), str(wrapper)],
                        "paths", True, 0, {str(stable): "a" * 64},
                        {**sources, "/tmp/foreign.py": "d" * 64}):
            with self.subTest(sources=repr(invalid)):
                changed = copy.deepcopy(good)
                changed["sources"] = invalid
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(changed, expected, {wrapper})
        # Mutable/allowed files still need a real 64-hex SHA-256 string.
        for invalid in (None, [], {}, True, 10, "not-a-sha"):
            changed = copy.deepcopy(good)
            changed["sources"][str(wrapper)] = invalid
            with self.subTest(hash_value=repr(invalid)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_ADMISSION_SOURCE_HASH$"):
                    check(changed, expected, {wrapper})
        changed = copy.deepcopy(good)
        changed["sources"][str(stable)] = "e" * 64
        with self.assertRaisesRegex(
                RuntimeError, "^HOLD_PREVIOUS_ADMISSION_STABLE_SOURCE$"):
            check(changed, expected, {wrapper})



class PreviousTrainingReceiptEnvelopeFence(unittest.TestCase):
    def test_previous_receipt_root_and_owner_lineage_fail_closed(self):
        # Actual source AST, without launching any native trainer or server job.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "verify_previous_training_receipt")
        ns = {"SCHEMA": "NOX_OWNER_TRAINING_RESUME_V1",
              "SERVICE": "nox-train-volta-t866u", "re": re}
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     str(SOURCE), "exec"), ns)
        check = ns["verify_previous_training_receipt"]
        boost, memory, media = ({"request": "boost"},
                                {"request": "s03"}, {"request": "media"})
        pointer = {
            "source_sha": "a" * 40,
            "dispatcher_upgrade": boost,
            "s03_activation": memory,
            "media_acceptance": media,
        }
        policy = {
            "training_allowed": True,
            "training_service": ns["SERVICE"],
        }
        previous = {
            "schema": ns["SCHEMA"],
            "state": "TRAINING_CHECKPOINTED_BY_NEW_PAUSE",
            "training_started": True,
            "source_sha": pointer["source_sha"],
            "admission": copy.deepcopy(pointer),
            "dispatcher_upgrade": copy.deepcopy(boost),
            "s03_activation": copy.deepcopy(memory),
            "media_acceptance": copy.deepcopy(media),
        }
        self.assertTrue(check(copy.deepcopy(previous), pointer, policy,
                              boost, memory, media))
        # A durable HOLD or an unrecognized/missing predecessor state must not
        # be reusable as a successful owner source/optimizer lineage.
        for invalid_state in ("HOLD_TRAINING_RESUME", "HOLD_OWNER_STOP",
                              "TRAINING_ACCEPTED", "UNVERIFIED_COMPLETE",
                              None, [], {}, True, 1000):
            with self.subTest(previous_state=repr(invalid_state)):
                changed = copy.deepcopy(previous)
                changed["state"] = invalid_state
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(changed, pointer, policy, boost, memory, media)
        for bad_started in (False, None, 1, "true", []):
            with self.subTest(training_started=repr(bad_started)):
                changed = copy.deepcopy(previous)
                changed["training_started"] = bad_started
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(changed, pointer, policy, boost, memory, media)
        for accepted in (
                "BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING",
                "EXISTING_CONTINUATION_RUNNING",
                "FIVE_STEPS_VERIFIED_CONTINUATION_DEFERRED",
                "FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED",
                "FIVE_STEPS_VERIFIED_CONTINUATION_STARTED",
                "CONTINUATION_CHECKPOINTED_BY_OWNER_PAUSE",
                "CONTINUATION_TARGET_1000_COMPLETED"):
            with self.subTest(accepted_state=accepted):
                changed = copy.deepcopy(previous)
                changed["state"] = accepted
                self.assertTrue(check(changed, pointer, policy, boost, memory,
                                      media))
        for invalid in (None, [], ["receipt"], True, False, 17, 1.5,
                        "receipt"):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(invalid, pointer, policy, boost, memory, media)
        for key in ("schema", "state", "training_started", "source_sha", "admission",
                    "dispatcher_upgrade", "s03_activation", "media_acceptance"):
            with self.subTest(missing=key):
                changed = copy.deepcopy(previous)
                changed.pop(key)
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(changed, pointer, policy, boost, memory, media)
        for invalid in (None, [], True):
            with self.subTest(pointer=repr(invalid)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(previous, invalid, policy, boost, memory, media)
            with self.subTest(policy=repr(invalid)):
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(previous, pointer, invalid, boost, memory, media)
        unowned = copy.deepcopy(policy)
        unowned["training_allowed"] = 1
        with self.assertRaisesRegex(
                RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
            check(previous, pointer, unowned, boost, memory, media)

        # R25: a separately supplied prior admission pointer can be a dict
        # with no source_sha. That must produce a durable owner-lineage HOLD,
        # not an uncaught KeyError from pointer['source_sha'].
        for invalid in ("__MISSING__", None, [], True, "a" * 39,
                        "A" * 40, "not-a-commit"):
            with self.subTest(pointer_source_sha=repr(invalid)):
                changed = copy.deepcopy(pointer)
                if invalid == "__MISSING__":
                    changed.pop("source_sha")
                else:
                    changed["source_sha"] = invalid
                with self.assertRaisesRegex(
                        RuntimeError, "^HOLD_PREVIOUS_TRAINING_RECEIPT$"):
                    check(previous, changed, policy, boost, memory, media)



class EmbeddedOwnerBoostPolicyDepthFence(unittest.TestCase):
    def test_bounded_deep_policy_denies_training_permission_without_exception(self):
        # Execute only the embedded real owner policy helper. No native trainer.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        assignment = next((node for node in tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name)
                                   and target.id == "PERMISSION_HELPER"
                                   for target in node.targets)), None)
        self.assertIsNotNone(assignment, "HOLD_EMBEDDED_PERMISSION_SOURCE_MISSING")
        helper_text = ast.literal_eval(assignment.value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            policy_path = state / "task_boost_mode.json"
            namespace = {"ROOT": root}
            exec(compile(helper_text, "<real-owner-permission>", "exec"), namespace)
            allowed = namespace["_nox_owner_training_allowed"]
            healthy = {
                "enabled": True, "mode": "TASK_BOOST",
                "training_allowed": True,
                "training_service": "nox-train-volta-t866u",
                "training_request": "__NOX_OWNER_REQUEST_ID__",
                "training_source_sha": "__NOX_OWNER_SOURCE_SHA__",
            }
            policy_path.write_text(json.dumps(healthy), encoding="utf-8")
            self.assertIs(allowed(), True)
            # Even under the real 16,000-byte read bound, valid JSON may
            # exceed Python's maximum nesting depth and raise RecursionError.
            depth = 6000
            hostile = (b'{"enabled":true,"padding":' + b'[' * depth
                       + b'0' + b']' * depth + b'}')
            self.assertLess(len(hostile), 16000)
            policy_path.write_bytes(hostile)
            self.assertIs(allowed(), False)
            # No lingering permission / descriptor corruption after denial.
            policy_path.write_text(json.dumps(healthy), encoding="utf-8")
            self.assertIs(allowed(), True)


if __name__ == "__main__":
    unittest.main()
