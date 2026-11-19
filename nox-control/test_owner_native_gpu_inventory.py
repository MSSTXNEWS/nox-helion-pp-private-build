import contextlib
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import owner_native_gpu_inventory as gpu


BOOT = "91e8d52f-1f5e-4c1c-a1fb-08dcf394f123"
GPU_A = "GPU-58f4970e-117b-ea29-9c68-b65c5ca88fd0"
GPU_B = "GPU-db9e6c65-6c6a-83c2-8304-e8605c5188bc"


def output(used_a=16000, free_a=16768, used_b=12000, free_b=20768,
           name_a="Tesla V100-SXM2-32GB", uuid_a=GPU_A, uuid_b=GPU_B):
    return (
        f"0, {name_a}, {uuid_a}, 32768, {used_a}, {free_a}\n"
        f"1, Tesla V100-SXM2-32GB, {uuid_b}, 32768, {used_b}, {free_b}\n"
    )


class FakeRunner:
    def __init__(self, outputs, returncodes=None):
        self.outputs = list(outputs)
        self.returncodes = list(returncodes or [0] * len(self.outputs))
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if not self.outputs:
            raise AssertionError("unexpected nvidia-smi invocation")
        return SimpleNamespace(returncode=self.returncodes.pop(0), stdout=self.outputs.pop(0), stderr="")


class ClockReader:
    def __init__(self, uptimes=None, boots=None):
        self.uptimes = iter(uptimes or [100.0, 100.1, 101.0, 101.1])
        self.boots = iter(boots or [BOOT] * 4)

    def __call__(self, path, limit):
        if path == "/proc/sys/kernel/random/boot_id":
            value = next(self.boots)
        elif path == "/proc/uptime":
            value = str(next(self.uptimes)) + " 0.0"
        else:
            raise AssertionError("unexpected host clock path")
        if len(value) > limit:
            raise AssertionError("test fixture exceeded read bound")
        return value


class GpuInventoryTests(unittest.TestCase):
    def test_parse_exact_two_v100_rows_with_uuid_and_memory(self):
        rows = gpu.parse_gpu_rows(output())
        self.assertEqual([r["index"] for r in rows], [0, 1])
        self.assertEqual([r["uuid"] for r in rows], [GPU_A, GPU_B])
        self.assertEqual(rows[0]["memory_total_mib"], 32768)
        self.assertEqual(rows[0]["memory_free_mib"], 16768)
        self.assertEqual(rows[1]["memory_used_mib"], 12000)

    def test_builds_two_snapshots_and_binds_stable_boot_and_identity(self):
        runner = FakeRunner([output(), output(used_a=16100, free_a=16668,
                                                  used_b=12100, free_b=20668)])
        ticks = iter([1, 2, 3, 4])
        sleeps = []
        result = gpu.build_inventory(
            run=runner,
            read_text=ClockReader(),
            monotonic_ns=lambda: next(ticks),
            sleep=sleeps.append,
        )
        self.assertTrue(result["identity_stable"])
        self.assertEqual(result["boot_id"], BOOT)
        self.assertEqual(result["snapshots"][0]["rows"][0]["memory_used_mib"], 16000)
        self.assertEqual(result["snapshots"][1]["rows"][0]["memory_used_mib"], 16100)
        self.assertEqual(sleeps, [0.5])
        self.assertEqual(len(runner.calls), 2)
        for args, kwargs in runner.calls:
            self.assertEqual(args, [gpu.NVIDIA_SMI, *gpu.QUERY])
            self.assertEqual(kwargs["timeout"], 12)
            self.assertTrue(kwargs["capture_output"])
            self.assertTrue(kwargs["text"])

    def test_source_request_and_action_pins_are_required(self):
        base = {"NOX_OWNER_SOURCE_SHA": "a" * 40, "NOX_OWNER_REQUEST_ID": "7000000000",
                "NOX_OWNER_ACTION": "gpu_inventory", "NOX_OWNER_INSTANCE_ID": "60509551"}
        runner = FakeRunner([output(), output()])
        receipt = gpu.run_action(env=base, run=runner, read_text=ClockReader(),
                                 monotonic_ns=iter([1, 2, 3, 4]).__next__, sleep=lambda _: None)
        self.assertEqual(receipt["source_sha"], "a" * 40)
        self.assertEqual(receipt["request_id"], 7000000000)
        self.assertEqual(receipt["instance_id"], 60509551)
        self.assertEqual(receipt["schema"], "NOX_GPU_INVENTORY_V1")
        self.assertEqual(len(receipt["inventory"]["snapshots"]), 2)
        self.assertRegex(receipt["inventory_sha256"], r"^[0-9a-f]{64}$")
        for key, value in (("NOX_OWNER_ACTION", "audit"),
                           ("NOX_OWNER_SOURCE_SHA", "bad"),
                           ("NOX_OWNER_REQUEST_ID", "0"),
                           ("NOX_OWNER_INSTANCE_ID", "60509552")):
            with self.subTest(key=key):
                invalid = dict(base, **{key: value})
                with self.assertRaisesRegex(RuntimeError, "^HOLD_GPU_INVENTORY_"):
                    gpu.run_action(env=invalid, run=runner)

    def test_rejects_duplicate_index_and_uuid(self):
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_INDEX"):
            gpu.parse_gpu_rows("0, Tesla V100-SXM2-32GB, " + GPU_A + ", 32768, 100, 32668\n"
                               "0, Tesla V100-SXM2-32GB, " + GPU_B + ", 32768, 100, 32668\n")
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_UUID"):
            gpu.parse_gpu_rows("0, Tesla V100-SXM2-32GB, " + GPU_A + ", 32768, 100, 32668\n"
                               "1, Tesla V100-SXM2-32GB, " + GPU_A + ", 32768, 100, 32668\n")

    def test_rejects_wrong_gpu_count_and_non_v100(self):
        with self.assertRaisesRegex(RuntimeError, "GPU_COUNT"):
            gpu.parse_gpu_rows("0, Tesla V100-SXM2-32GB, " + GPU_A + ", 32768, 100, 32668\n")
        with self.assertRaisesRegex(RuntimeError, "IDENTITY"):
            gpu.parse_gpu_rows(output(name_a="NVIDIA A100-SXM4-40GB"))

    def test_memory_holds_separate_format_range_and_sum_with_safe_numeric_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, "MEMORY_SUM") as caught:
            gpu.parse_gpu_rows(output(used_a=20000, free_a=20000))
        diagnostic = caught.exception.memory_diagnostic
        self.assertEqual(diagnostic, [{
            "index": 0, "total_mib": 32768, "used_mib": 20000,
            "free_mib": 20000, "residual_mib": -7232,
        }])
        self.assertNotIn(GPU_A, repr(diagnostic))
        self.assertNotIn("model", repr(diagnostic))
        with self.assertRaisesRegex(RuntimeError, "MEMORY_RANGE"):
            gpu.parse_gpu_rows(output(used_a=32769, free_a=1))
        with self.assertRaisesRegex(RuntimeError, "MEMORY_FORMAT"):
            gpu.parse_gpu_rows(output(used_a="N/A", free_a=100))
        with self.assertRaisesRegex(RuntimeError, "ROW_SHAPE"):
            gpu.parse_gpu_rows("0, Tesla V100-SXM2-32GB, " + GPU_A + ", 32768, 100" + chr(10))

    def test_main_emits_only_fixed_hold_and_identity_free_memory_diagnostic(self):
        diagnostic = [{
            "index": 0, "total_mib": 32768, "used_mib": 16462,
            "free_mib": 16300, "residual_mib": 6,
        }]
        stdout = io.StringIO()
        with patch.object(gpu, "run_action",
                          side_effect=gpu.GPUInventoryHold("HOLD_GPU_INVENTORY_MEMORY_SUM",
                                                           memory_diagnostic=diagnostic)):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(gpu.main(), 2)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[0], "NOX_MAINT_GPU_INVENTORY_RESULT=HOLD_GPU_INVENTORY_MEMORY_SUM")
        self.assertTrue(lines[1].startswith(gpu.MEMORY_DIAGNOSTIC_PREFIX))
        self.assertNotIn(GPU_A, stdout.getvalue())
        self.assertNotIn("stderr", stdout.getvalue())

    def test_rejects_oversized_output_and_nonzero_nvidia_smi(self):
        with self.assertRaisesRegex(RuntimeError, "OUTPUT_BOUND"):
            gpu.parse_gpu_rows("x" * (gpu.MAX_OUTPUT_BYTES + 1))
        runner = FakeRunner([output()], returncodes=[1])
        with self.assertRaisesRegex(RuntimeError, "NVIDIA_SMI_RC"):
            gpu.capture_snapshot(run=runner, read_text=ClockReader(),
                                 monotonic_ns=iter([1, 2]).__next__)

    def test_rejects_clock_boot_change_during_capture(self):
        reader = ClockReader(boots=[BOOT, "a1e8d52f-1f5e-4c1c-a1fb-08dcf394f123"])
        runner = FakeRunner([output()])
        with self.assertRaisesRegex(RuntimeError, "CLOCK_DRIFT"):
            gpu.capture_snapshot(run=runner, read_text=reader,
                                 monotonic_ns=iter([1, 2]).__next__)

    def test_rejects_boot_or_device_drift_between_snapshots(self):
        reader = ClockReader(uptimes=[100.0, 100.1, 101.0, 101.1],
                             boots=[BOOT, BOOT, "a1e8d52f-1f5e-4c1c-a1fb-08dcf394f123", "a1e8d52f-1f5e-4c1c-a1fb-08dcf394f123"])
        with self.assertRaisesRegex(RuntimeError, "BOOT_OR_UPTIME"):
            gpu.build_inventory(run=FakeRunner([output(), output()]), read_text=reader,
                                monotonic_ns=iter([1, 2, 3, 4]).__next__, sleep=lambda _: None)
        changed = output(uuid_b="GPU-a1e8d52f-1f5e-4c1c-a1fb-08dcf394f123")
        with self.assertRaisesRegex(RuntimeError, "DEVICE_DRIFT"):
            gpu.build_inventory(run=FakeRunner([output(), changed]), read_text=ClockReader(),
                                monotonic_ns=iter([1, 2, 3, 4]).__next__, sleep=lambda _: None)

    def test_success_marker_is_terminal_and_failure_never_marks_complete(self):
        receipt = {"schema": "NOX_GPU_INVENTORY_V1", "source_sha": "a" * 40, "request_id": 17}
        stdout = io.StringIO()
        with patch.object(gpu, "run_action", return_value=receipt):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(gpu.main(), 0)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[-1], "NOX_MAINT_GPU_INVENTORY_COMPLETE=true")
        self.assertEqual(lines[0].split("=", 1)[0], "NOX_MAINT_GPU_INVENTORY")
        stdout = io.StringIO()
        with patch.object(gpu, "run_action", side_effect=RuntimeError("HOLD_GPU_INVENTORY_TEST")):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(gpu.main(), 2)
        self.assertNotIn("NOX_MAINT_GPU_INVENTORY_COMPLETE=true", stdout.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
