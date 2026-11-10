"""Original WPF HWND witness: tiny helper windows cannot prove installed GUI.

Only mocked Win32 source regression; NOT a Windows runtime or E07 result.
"""
from __future__ import annotations

import ctypes
import importlib.util
from ctypes import wintypes
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_windows_hwnd_witness.py"
spec = importlib.util.spec_from_file_location("nox_t06_windows_hwnd_geometry", SOURCE)
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)


class FakeUser32:
    def __init__(self, *, pid=9001, width=1024, height=720,
                 class_name="HwndWrapper[NOX.P01.Shell.exe;;opaque]",
                 visible=True, owner=0, geometry_ok=True, enumeration_ok=True):
        self.pid, self.width, self.height = pid, width, height
        self.class_name, self.visible, self.owner = class_name, visible, owner
        self.geometry_ok, self.enumeration_ok = geometry_ok, enumeration_ok
        self.geometry_calls = 0

    def GetWindowThreadProcessId(self, hwnd, dest):
        ctypes.cast(dest, ctypes.POINTER(wintypes.DWORD)).contents.value = self.pid
        return 42

    def IsWindow(self, hwnd):
        return True

    def IsWindowVisible(self, hwnd):
        return self.visible

    def GetWindow(self, hwnd, flag):
        return self.owner

    def GetClassNameW(self, hwnd, dest, count):
        dest.value = self.class_name
        return len(self.class_name)

    def GetClientRect(self, hwnd, dest):
        self.geometry_calls += 1
        if not self.geometry_ok:
            return False
        rect = ctypes.cast(dest, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, self.width, self.height
        return True

    def EnumWindows(self, callback, lparam):
        callback(177, lparam)
        return self.enumeration_ok


class NativeWpfHwndGeometryTests(unittest.TestCase):
    def check(self, fake, expected):
        actual = witness._visible_window_for_pid(9001, fake, lambda fn: fn)
        self.assertEqual(actual, 177 if expected else None)

    def test_fullsize_original_wpf_window_admitted(self):
        fake = FakeUser32()
        self.check(fake, True)
        self.assertGreaterEqual(fake.geometry_calls, 2)

    def test_tiny_same_pid_wpf_helper_cannot_impersonate_main_window(self):
        for width, height in ((0, 720), (1024, 0), (1, 1), (159, 500), (500, 99)):
            with self.subTest(width=width, height=height):
                self.check(FakeUser32(width=width, height=height), False)

    def test_geometry_query_failure_is_hold_not_gui_pass(self):
        self.check(FakeUser32(geometry_ok=False), False)

    def test_wrong_pid_class_hidden_owned_and_failed_enumeration_remain_denied(self):
        for opt in ({'pid': 44}, {'class_name':'ConsoleWindowClass'},
                    {'visible':False}, {'owner':888}, {'enumeration_ok':False}):
            with self.subTest(opts=opt):
                self.check(FakeUser32(**opt), False)


if __name__ == "__main__":
    unittest.main()
