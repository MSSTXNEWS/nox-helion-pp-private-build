"""G3-A R07 source-only regression: no DOS console device masquerading as local GGUF.

Run from the repository root:
python -m unittest discover -s Packages/P03/Admission -p 'test_g3a_r07_windows_reserved_device_guard.py' -v

A PASS tests lexical path gating only, NOT native ACL/reparse/file bytes or Windows E2E.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p03_modelcenter_gate import _windows_local_gguf_path


class G3AR07WindowsReservedDeviceGuardTests(unittest.TestCase):
    def test_console_input_device_with_gguf_extension_is_rejected(self):
        self.assertFalse(_windows_local_gguf_path(r"C:\models\CONIN$.gguf"))

    def test_console_output_device_with_gguf_extension_is_rejected(self):
        self.assertFalse(_windows_local_gguf_path(r"C:\models\CONOUT$.gguf"))

    def test_console_device_names_are_case_insensitive(self):
        for name in ("conin$.gguf", "conout$.GGUF", "CoNiN$.gguf", "CoNoUt$.gguf"):
            with self.subTest(name=name):
                self.assertFalse(_windows_local_gguf_path("D:\\weights\\" + name))

    def test_console_devices_cannot_appear_as_parent_components(self):
        for name in ("CONIN$", "CONOUT$", "ConIn$", "conout$"):
            with self.subTest(name=name):
                self.assertFalse(_windows_local_gguf_path("C:\\" + name + r"\qwen.gguf"))

    def test_unrelated_normal_local_gguf_paths_remain_accepted(self):
        for path in (r"C:\models\qwen.gguf", r"D:\weights\conin-model.gguf",
                     r"E:\models\conout_v2.gguf"):
            with self.subTest(path=path):
                self.assertTrue(_windows_local_gguf_path(path))

    def test_existing_reserved_names_remain_rejected(self):
        for name in ("CON.gguf", "AUX.gguf", "NUL.gguf", "PRN.gguf",
                     "COM1.gguf", "LPT9.gguf", "COM¹.gguf"):
            with self.subTest(name=name):
                self.assertFalse(_windows_local_gguf_path("C:\\models\\" + name))

    def test_unc_and_win32_device_namespace_paths_stay_rejected(self):
        self.assertFalse(_windows_local_gguf_path(r"\\server\share\qwen.gguf"))
        self.assertFalse(_windows_local_gguf_path(r"\\?\C:\models\qwen.gguf"))

    def test_relative_paths_stay_rejected(self):
        self.assertFalse(_windows_local_gguf_path(r"models\qwen.gguf"))


if __name__ == "__main__":
    unittest.main()
