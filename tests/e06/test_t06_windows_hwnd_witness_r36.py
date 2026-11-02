"""MB2/R36: no log-only WPF GUI PASS; physical Windows HWND proof is required.

Pure Win32 API contract fakes run on Linux as well. Real GUI/IPC and E07
remain NOT_RUN until an authorized Windows x64 runner executes the code.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "coordination/e06/t06_windows_hwnd_witness.py"

spec = importlib.util.spec_from_file_location("hwnd_witness", MODULE)
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)


class FakeUser32:
    def __init__(self, windows):
        self.windows = windows

    def EnumWindows(self, callback, unused):
        for hwnd in self.windows:
            if not callback(hwnd, 0):
                break
        return 1

    def GetWindowThreadProcessId(self, hwnd, pid_pointer):
        pid = self.windows[hwnd]["pid"]
        ctypes.cast(pid_pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = pid
        return 1

    def IsWindow(self, hwnd):
        return int(self.windows[hwnd].get("exists", True))

    def IsWindowVisible(self, hwnd):
        return int(self.windows[hwnd].get("visible", False))

    def GetWindow(self, hwnd, flag):
        if flag != 4:
            raise AssertionError("unexpected Win32 owner query")
        return int(self.windows[hwnd].get("owner", 0))


class OriginalWpfHwndContract(unittest.TestCase):
    def scan(self, pid, windows):
        return witness._visible_window_for_pid(pid, FakeUser32(windows), lambda cb: cb)

    def test_only_launched_pid_visible_unowned_top_level_accepted(self):
        windows = {
            11: {"pid": 40, "visible": True},
            22: {"pid": 55, "visible": False},
            33: {"pid": 55, "visible": True, "owner": 88},
            44: {"pid": 55, "visible": True},
        }
        self.assertEqual(self.scan(55, windows), 44)
        self.assertIsNone(self.scan(41, windows))

    def test_hidden_owned_destroyed_and_nonmatching_are_denied(self):
        windows = {
            11: {"pid": 52, "visible": False},
            12: {"pid": 52, "visible": True, "owner": 9},
            13: {"pid": 52, "visible": True, "exists": False},
            14: {"pid": 21, "visible": True},
        }
        self.assertIsNone(self.scan(52, windows))

    def test_invalid_pid_is_denied(self):
        for bad in (0, -1, True, "100", None):
            with self.subTest(bad=bad):
                self.assertIsNone(self.scan(bad, {10: {"pid": 1, "visible": True}}))

    def test_real_platform_guard_denies_non_windows(self):
        import sys
        if sys.platform != "win32":
            self.assertIsNone(witness.find_visible_wpf_hwnd(12345))


if __name__ == "__main__":
    unittest.main()
