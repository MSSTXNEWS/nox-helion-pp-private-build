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
    def __init__(self, windows, enum_success=True):
        self.windows = windows
        self.enum_success = enum_success

    def EnumWindows(self, callback, unused):
        for hwnd in self.windows:
            if not callback(hwnd, 0):
                break
        return int(self.enum_success)

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

    def GetClassNameW(self, hwnd, dest, length):
        # Real ctypes Win32 call returns a plain int and writes WCHARs.
        name = self.windows[hwnd].get("class", "HwndWrapper[NOX.EXE;;main]")
        dest.value = name[:length - 1]
        if self.windows[hwnd].get("retire_after_class"):
            self.windows[hwnd]["exists"] = False
        return len(dest.value)


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

    def test_first_matching_wpf_window_retired_before_second_pass_uses_stable_main(self):
        windows = {
            11: {"pid": 55, "visible": True, "retire_after_class": True},
            22: {"pid": 55, "visible": True},
        }
        # Splash is already gone by final proof; MainWindow remains live.
        self.assertEqual(self.scan(55, windows), 22)

    def test_failed_enumwindows_must_not_certify_partial_gui(self):
        windows = {22: {"pid": 55, "visible": True}}
        api = FakeUser32(windows, enum_success=False)
        self.assertIsNone(witness._visible_window_for_pid(55, api, lambda cb: cb))

    def test_only_wpf_class_counts_not_a_generic_same_pid_dialog(self):
        windows = {
            11: {"pid": 55, "visible": True, "class": "#32770"},
            22: {"pid": 55, "visible": True, "class": "HwndWrapper[NOX.EXE;;main]"},
        }
        self.assertEqual(self.scan(55, windows), 22)
        self.assertIsNone(self.scan(55, {11: windows[11]}))

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
