"""Source-only contract checks for Maya's pinned DeepSeek-V4.1 runtime.

These checks fetch only immutable upstream source text. They do not load a model,
run CUDA, test the installed binary, or prove runtime compatibility.
"""
from __future__ import annotations

import urllib.request
import unittest

MAYA_REPO = "mw00/project-maya"
MAYA_COMMIT = "c81fab6c9d63cf69b928f92460e0a662b28aa9ec"
BASE = f"https://raw.githubusercontent.com/{MAYA_REPO}/{MAYA_COMMIT}/"


def source(path: str) -> str:
    request = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "NOX-source-contract-test/1"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise AssertionError(f"{path}: HTTP {response.status}")
        return response.read().decode("utf-8")


class MayaDS4SourceCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packer = source("tools/ds4/pack_gguf.py")
        cls.kernels = source("src/ds4/ds4_iq.cu")
        cls.cmake = source("CMakeLists.txt")

    def test_packer_maps_iq2_xxs_and_deepseek_architecture(self) -> None:
        self.assertIn('16: ("IQ2_XXS", 256, 66)', self.packer)
        self.assertIn('kv["general.architecture"]', self.packer)
        self.assertIn('not in ("deepseek41",)', self.packer)

    def test_packer_accepts_engram_side_files(self) -> None:
        self.assertIn('ap.add_argument("--engram"', self.packer)
        self.assertIn('g.kv.get("general.architecture") == "deepseek41-engram"', self.packer)
        self.assertIn("ple_to_engram(kv)", self.packer)
        self.assertIn('raise SystemExit("--without: the Engram tables then come from --engram\'s set - name it")',
                      self.packer)

    def test_cuda_source_has_iq2_xxs_kernel_and_dispatch(self) -> None:
        self.assertIn("template <> struct Ty<kIQ2_XXS>", self.kernels)
        self.assertIn("case kIQ2_XXS: F(kIQ2_XXS); break;", self.kernels)
        self.assertIn("case kIQ2_XXS: return Ty<kIQ2_XXS>::B;", self.kernels)

    def test_cmake_source_allows_volta_sm70(self) -> None:
        self.assertIn("Volta (sm_70: GLM, maya-ds4 and maya-mm3 run on V100s)", self.cmake)
        self.assertIn("CMAKE_CUDA_ARCHITECTURES", self.cmake)
        self.assertIn("Maya: CUDA enabled, arch", self.cmake)


if __name__ == "__main__":
    unittest.main()
