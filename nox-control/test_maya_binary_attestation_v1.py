"""Synthetic tests for read-only Maya binary/build attestation; never invokes CUDA/Maya."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import maya_binary_attestation_v1 as attestation


class MayaBinaryAttestationTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        build = Path(temp.name) / "build"
        build.mkdir()
        binary = build / "maya-ds4"
        data = b"synthetic ELF/cubin placeholder"
        binary.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        (build / "CMakeCache.txt").write_text(
            "CMAKE_CUDA_ARCHITECTURES:STRING=70\n"
            "CMAKE_CUDA_COMPILER_VERSION:INTERNAL=12.4.1\n"
        )
        return binary, sha

    def invoke(self, binary, sha, *, elf_report="ELF file 1: sm_70\n"):
        result = subprocess.CompletedProcess(
            args=["cuobjdump", "--list-elf", str(binary)],
            returncode=0,
            stdout=elf_report,
            stderr="",
        )
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha), \
             patch.object(attestation.shutil, "which", return_value="/fake/cuobjdump"), \
             patch.object(attestation.subprocess, "run", return_value=result) as run:
            got = attestation.attest_maya_binary(binary, sha)
        return got, run

    def test_requires_real_sha_cache_architecture_and_sm70_elf_report(self):
        binary, sha = self.fixture()
        got, run = self.invoke(binary, sha)
        self.assertEqual(got["state"], "BINARY_BUILD_ATTESTED_SOURCE_ONLY")
        self.assertEqual(got["binary_sha256"], sha)
        self.assertEqual(got["cuda_architectures"], "70")
        self.assertTrue(got["embedded_sm70_elf"])
        self.assertFalse(got["measured"])
        run.assert_called_once_with(
            ["/fake/cuobjdump", "--list-elf", str(binary)],
            capture_output=True, text=True, timeout=30, check=False,
        )

    def test_wrong_cuda_architecture_holds_before_elf_inspection(self):
        binary, sha = self.fixture()
        cache = binary.parent / "CMakeCache.txt"
        cache.write_text("CMAKE_CUDA_ARCHITECTURES:STRING=120\n")
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha), \
             patch.object(attestation.shutil, "which", return_value="/fake/cuobjdump"), \
             patch.object(attestation.subprocess, "run") as run:
            got = attestation.attest_maya_binary(binary, sha)
        self.assertEqual(got["state"], "HOLD_MAYA_CMAKE_CUDA_ARCHITECTURES")
        run.assert_not_called()

    def test_missing_sm70_elf_holds(self):
        binary, sha = self.fixture()
        got, _ = self.invoke(binary, sha, elf_report="ELF file 1: sm_120\n")
        self.assertEqual(got["state"], "HOLD_MAYA_SM70_ELF_MISSING")

    def test_symlink_binary_path_holds(self):
        binary, sha = self.fixture()
        link = binary.parent / "maya-link"
        link.symlink_to(binary)
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha), \
             patch.object(attestation.subprocess, "run") as run:
            got = attestation.attest_maya_binary(link, sha)
        self.assertEqual(got["state"], "HOLD_MAYA_BINARY_PATH_SYMLINK")
        run.assert_not_called()

    def test_path_replaced_after_sha_during_elf_inspection_holds(self):
        binary, sha = self.fixture()
        replacement = binary.parent / "replacement"
        replacement.write_bytes(b"replacement binary bytes")
        result = subprocess.CompletedProcess(
            args=["cuobjdump", "--list-elf", str(binary)],
            returncode=0, stdout="ELF file 1: sm_70\\n", stderr="",
        )
        def swap_during_inspection(*args, **kwargs):
            os.replace(replacement, binary)
            return result
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha), \
             patch.object(attestation.shutil, "which", return_value="/fake/cuobjdump"), \
             patch.object(attestation.subprocess, "run", side_effect=swap_during_inspection):
            got = attestation.attest_maya_binary(binary, sha)
        self.assertEqual(got["state"], "HOLD_MAYA_BINARY_CHANGED_AFTER_HASH")

    def test_sha_mismatch_holds_before_build_metadata(self):
        binary, sha = self.fixture()
        binary.write_bytes(b"changed after expected digest")
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha):
            got = attestation.attest_maya_binary(binary, sha)
        self.assertEqual(got["state"], "HOLD_MAYA_BINARY_SHA256")

    def test_missing_cmake_cache_holds(self):
        binary, sha = self.fixture()
        (binary.parent / "CMakeCache.txt").unlink()
        with patch.object(attestation, "PINNED_BINARY_SHA256", sha):
            got = attestation.attest_maya_binary(binary, sha)
        self.assertEqual(got["state"], "HOLD_MAYA_BINARY_UNREADABLE")


if __name__ == "__main__":
    unittest.main()
