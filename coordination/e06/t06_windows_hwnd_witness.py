"""Read-only Win32 proof of a *visible, unowned* top-level WPF window.

For the original NOX EXPRESS same-VM candidate only. A shell log and live
process alone do not demonstrate that the installed GUI actually launched.
Do not use this witness to claim independent E07 or grant native consent.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


_GW_OWNER = 4


def _visible_window_for_pid(pid: int, user32: object, callback_type: object) -> int | None:
    """Isolated Win32 enumeration, accepting no HWND from a different PID."""
    if type(pid) is not int or pid <= 0:
        return None
    matches: list[int] = []

    def inspect(hwnd: int, _lparam: int) -> bool:
        actual_pid = wintypes.DWORD(0)
        thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(actual_pid))
        if (thread_id and actual_pid.value == pid and
                user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd) and
                not user32.GetWindow(hwnd, _GW_OWNER)):
            matches.append(int(hwnd))
            return False  # intentionally stop EnumWindows on the first match
        return True

    callback = callback_type(inspect)  # retain callback throughout EnumWindows
    user32.EnumWindows(callback, 0)
    return matches[0] if matches else None


def find_visible_wpf_hwnd(pid: int) -> int | None:
    """Witness an actual window of the launched WPF PID; fail closed."""
    if sys.platform != "win32" or type(pid) is not int or pid <= 0:
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        return _visible_window_for_pid(pid, user32, callback_type)
    except (AttributeError, OSError, TypeError, ValueError):
        return None
