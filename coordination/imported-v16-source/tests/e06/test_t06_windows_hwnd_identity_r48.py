"""R48: an arbitrary live PID window is not proof of the original WPF shell.

Runs without a Windows desktop: fake user32 exercises the actual native witness
selection logic. Real HWND/WebView2/IPC and installed E07 remain HOLD.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import importlib.util
from pathlib import Path
import unittest

WITNESS = Path(__file__).resolve().parents[2] / "coordination/e06/t06_windows_hwnd_witness.py"
spec = importlib.util.spec_from_file_location("nox_t06_hwnd_witness", WITNESS)
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)


class FakeUser32:
    def __init__(self, windows, *, replace_after_enum=None):
        self.windows = windows
        self.replace_after_enum = replace_after_enum

    def EnumWindows(self, callback, _):
        for hwnd in list(self.windows):
            if callback(hwnd, 0) is False:
                break
        if self.replace_after_enum:
            self.replace_after_enum(self.windows)
        return True

    def GetWindowThreadProcessId(self, hwnd, out_pid):
        row = self.windows.get(hwnd)
        if row is None:
            return 0
        ctypes.cast(out_pid, ctypes.POINTER(wintypes.DWORD))[0] = row["pid"]
        return 41

    def IsWindow(self, hwnd):
        return hwnd in self.windows

    def IsWindowVisible(self, hwnd):
        return self.windows[hwnd]["visible"]

    def GetWindow(self, hwnd, _which):
        return self.windows[hwnd]["owner"]

    def GetClassNameW(self, hwnd, output, length):
        value = self.windows[hwnd]["class"]
        if not value or len(value) >= length:
            return 0
        output.value = value
        return len(value)


def window(pid, *, cls="HwndWrapper[NOX.P01.Shell.exe;;test]", visible=True, owner=0):
    return {"pid": pid, "class": cls, "visible": visible, "owner": owner}


class WpfLiveHwndIdentity(unittest.TestCase):
    def probe(self, windows, *, replace_after_enum=None, pid=731):
        return witness._visible_window_for_pid(
            pid, FakeUser32(windows, replace_after_enum=replace_after_enum), lambda f: f)

    def test_real_wpf_wrapper_of_exact_pid_accepted(self):
        self.assertEqual(self.probe({101: window(731)}), 101)

    def test_arbitrary_visible_non_wpf_dialog_cannot_prove_wpf_gui(self):
        self.assertIsNone(self.probe({101: window(731, cls="ConsoleWindowClass")}))

    def test_foreign_pid_ignored_even_with_genuine_wpf_class(self):
        self.assertEqual(self.probe({100: window(123), 101: window(731)}), 101)

    def test_owned_or_hidden_wpf_window_not_accepted(self):
        self.assertIsNone(self.probe({101: window(731, owner=123)}))
        self.assertIsNone(self.probe({101: window(731, visible=False)}))

    def test_hwnd_reparent_or_pid_reuse_after_enum_fails_closed(self):
        def swapped(rows):
            rows[101] = window(455, cls="HwndWrapper[foreign.exe;;changed]")
        self.assertIsNone(self.probe({101: window(731)}, replace_after_enum=swapped))

    def test_absent_class_and_bad_pid_rejected(self):
        self.assertIsNone(self.probe({101: window(731, cls="")}))
        self.assertIsNone(self.probe({101: window(731)}, pid=0))


if __name__ == "__main__":
    unittest.main()
