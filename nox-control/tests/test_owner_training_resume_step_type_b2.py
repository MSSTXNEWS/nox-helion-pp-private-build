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
            for invalid_loss in (-0.25, -1, -1e-300):
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
        self.assertEqual(ast.unparse(health[0].test),
                         "result['chat_after'].get('8080') != 200")
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

if __name__ == "__main__":
    unittest.main()
