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
FN_NAMES = {"read_json", "file_sha", "verify_paused_result", "resource_admission"}


def load_pinned_verifier(output):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in FN_NAMES]
    if {node.name for node in nodes} != FN_NAMES:
        raise AssertionError("HOLD_EXACT_OWNER_VERIFIER_MISSING")
    namespace = {
        "Path": Path, "hashlib": hashlib, "json": json, "math": math,
        "os": os, "stat": stat,
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


    def test_resource_admission_requires_actual_proxy_8080_not_legacy_8081(self):
        # Owner-confirmed 2026-11-19: proxy /health=200 on 8080; 8081 closed.
        # This source-only test never contacts the host or starts training.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            verifier = load_pinned_verifier(root)["resource_admission"]

            def fake_read_text(path, *args, **kwargs):
                contents = {
                    "/sys/fs/cgroup/cpu.max": "400000 100000",
                    "/sys/fs/cgroup/memory.max": "194065203200",
                    "/sys/fs/cgroup/memory.current": "188662734848",
                    str(root / "train_cpu_max.env"): "TRAIN_CPU_MAX=64GiB\n",
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
            verifier = load_pinned_verifier(root)["resource_admission"]
            sources = {
                "/sys/fs/cgroup/cpu.max": "max 100000",
                "/sys/fs/cgroup/memory.max": "194065203200",
                "/sys/fs/cgroup/memory.current": "188662734848",
                str(root / "train_cpu_max.env"): "TRAIN_CPU_MAX=64GiB\n",
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
            verify = load_pinned_verifier(root)["resource_admission"]
            maximum = 194065203200
            sources = {
                "/sys/fs/cgroup/cpu.max": "400000 100000",
                "/sys/fs/cgroup/memory.max": str(maximum),
                "/sys/fs/cgroup/memory.current": "188662734848",
                str(root / "train_cpu_max.env"): "TRAIN_CPU_MAX=64GiB\n",
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


if __name__ == "__main__":
    unittest.main()
