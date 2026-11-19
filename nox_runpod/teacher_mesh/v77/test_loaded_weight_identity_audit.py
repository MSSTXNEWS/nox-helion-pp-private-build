"""Offline fixture tests for the V77 loaded-weight identity witness."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from nox_runpod.teacher_mesh.v77 import loaded_weight_identity_audit as probe


def remote_namespace():
    body = probe.REMOTE.split("python3 - <<'PYREMOTE'\n", 1)[1].split("\nPYREMOTE", 1)[0]
    namespace = {"__name__": "v77_fixture_test"}
    exec(compile(body, "<v77-remote-inspector>", "exec"), namespace)
    return namespace


def make_stat(pid: int, start_ticks: int) -> bytes:
    fields = [b"S"] + [b"0"] * 19
    fields[19] = str(start_ticks).encode("ascii")
    return str(pid).encode("ascii") + b" (python3) " + b" ".join(fields) + b"\n"


class LoadedWeightIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        self.pid = 4242
        self.start_ticks = 773311
        self.proc_pid = self.proc / str(self.pid)
        self.proc_pid.mkdir(parents=True)
        self.cwd = self.root / "service-cwd"
        self.cwd.mkdir()
        (self.proc_pid / "cwd").symlink_to(self.cwd, target_is_directory=True)
        self.weight_dir = self.cwd / "deepseek_v41_flash_iq2xxs"
        self.weight_dir.mkdir()
        self.weight = self.weight_dir / "model-00001-of-00004.gguf"
        self.payload = b"fixture-weight-bytes-for-hash"
        self.weight.write_bytes(self.payload)
        self.write_process_facts(
            candidate="deepseek_v41_flash_iq2xxs/model-00001-of-00004.gguf"
        )
        self.write_maps(self.weight)

    def write_process_facts(self, candidate="deepseek_v41_flash_iq2xxs/model-00001-of-00004.gguf"):
        (self.proc_pid / "stat").write_bytes(make_stat(self.pid, self.start_ticks))
        (self.proc_pid / "cmdline").write_bytes(
            b"/usr/bin/python3\0model_server.py\0--model\0"
            + candidate.encode("utf-8") + b"\0"
        )

    def write_maps(self, mapped_file: Path):
        st = mapped_file.stat()
        line = (
            f"7f000000-7f001000 r--p 00000000 "
            f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x} "
            f"{st.st_ino} {mapped_file}\n"
        )
        (self.proc_pid / "maps").write_text(line, encoding="ascii")

    def inspect(self, ns=None, **kwargs):
        namespace = ns or remote_namespace()
        return namespace["inspect_loaded_weight"](
            supervisor_reader=lambda: self.pid,
            proc_root=self.proc,
            **kwargs,
        )

    def test_hashes_only_file_proven_in_process_maps_and_redacts_path(self):
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "VERIFIED_MAPPED_WEIGHT_FILE_SHA256")
        self.assertEqual(receipt["weight_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(receipt["weight_size_bytes"], len(self.payload))
        self.assertEqual(receipt["weight_identity"]["inode"], self.weight.stat().st_ino)
        self.assertEqual(receipt["pid"], self.pid)
        self.assertEqual(receipt["start_ticks"], self.start_ticks)
        self.assertEqual(receipt["callback_registry"]["state"], "UNKNOWN")
        self.assertEqual(receipt["model_identity"]["state"], "UNKNOWN")
        self.assertEqual(receipt["manifest_relation"]["state"], "UNKNOWN")
        encoded = json.dumps(receipt)
        self.assertNotIn("model-00001-of-00004.gguf", encoded)
        self.assertNotIn("deepseek_v41_flash_iq2xxs", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("--model", encoded)

    def test_pid_reuse_fails_closed(self):
        ns = remote_namespace()
        real = ns["process_start_ticks"]
        calls = 0

        def reused(pid, proc_root):
            nonlocal calls
            calls += 1
            return self.start_ticks if calls == 1 else self.start_ticks + 1

        ns["process_start_ticks"] = reused
        receipt = self.inspect(ns)
        ns["process_start_ticks"] = real
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_MODEL_PROCESS_REUSED")
        self.assertIsNone(receipt["weight_sha256"])

    def test_final_symlink_weight_is_rejected(self):
        target = self.cwd / "real.gguf"
        target.write_bytes(self.payload)
        link = self.cwd / "private_weight_name_DO_NOT_EXPORT.gguf"
        self.weight.unlink()
        link.symlink_to(target)
        self.write_process_facts()
        self.write_maps(target)
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_OPEN")
        self.assertIsNone(receipt["weight_sha256"])

    def test_weight_size_bound_returns_unknown(self):
        ns = remote_namespace()
        ns["MAX_WEIGHT_BYTES"] = len(self.payload) - 1
        receipt = self.inspect(ns)
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_SIZE_BOUNDS")

    def test_hash_time_bound_returns_unknown(self):
        receipt = self.inspect(hash_seconds=0)
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_HASH_BUDGET")

    def test_absent_model_file_returns_unknown_without_path_leak(self):
        missing = "absent_PRIVATE_WEIGHT_PATH.gguf"
        self.write_process_facts(candidate=missing)
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_OPEN")
        self.assertIsNone(receipt["weight_sha256"])
        self.assertEqual(receipt["manifest_relation"]["state"], "UNKNOWN")
        self.assertNotIn(missing, json.dumps(receipt))
        self.assertNotIn(str(self.cwd), json.dumps(receipt))

    def test_manifest_case_variant_is_never_used_as_fallback(self):
        # The process-selected lower-case file exists and is mapped. A
        # capitalized manifest-like candidate is absent and is never consulted.
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "VERIFIED_MAPPED_WEIGHT_FILE_SHA256")
        self.assertEqual(receipt["weight_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(
            receipt["manifest_relation"],
            {"state": "UNKNOWN", "reason": "PINNED_MANIFEST_NOT_READ_OR_USED"},
        )

    def test_missing_manifest_case_variant_does_not_hash_another_mapped_file(self):
        self.write_process_facts(candidate="DeepSeek/manifest-pinned.gguf")
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_OPEN")
        self.assertIsNone(receipt["weight_sha256"])
        self.assertNotIn("manifest-pinned.gguf", json.dumps(receipt))

    def test_unmapped_file_does_not_claim_loaded_identity(self):
        other = self.cwd / "unmapped.gguf"
        other.write_bytes(self.payload)
        self.write_process_facts(candidate=other.name)
        receipt = self.inspect()
        self.assertEqual(receipt["state"], "UNKNOWN")
        self.assertEqual(receipt["reason"], "HOLD_WEIGHT_NOT_MAPPED")
        self.assertIsNone(receipt["weight_sha256"])

    def test_remote_payload_compiles_without_native_execution(self):
        body = probe.REMOTE.split("python3 - <<'PYREMOTE'\n", 1)[1].split("\nPYREMOTE", 1)[0]
        compile(body, "<v77-remote-inspector>", "exec")
        self.assertIn("O_NOFOLLOW", body)
        self.assertIn("NATIVE_V77_PATHS_EXPORTED=false", body)
        self.assertIn("EXACT_LOADED_BRIDGE_SOURCE_NOT_PROVEN", body)

    def test_remote_hash_is_stable_and_bounded(self):
        first = probe.probe_source_hash()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, probe.probe_source_hash())
        self.assertLessEqual(probe.MAX_WEIGHT_BYTES, 16 * 1024 * 1024 * 1024)
        self.assertLessEqual(probe.MAX_HASH_SECONDS, 45)


if __name__ == "__main__":
    unittest.main()
