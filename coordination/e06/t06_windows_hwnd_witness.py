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
_WPF_CLASS_PREFIX = "HwndWrapper["


def _same_live_wpf_window(hwnd: int, pid: int, user32: object) -> bool:
    """A generic dialog/console of the right PID is NOT proof of WPF.

    GetClassNameW checks the real HwndSource class. Repeated after EnumWindows
    to reject a destroyed/reassigned HWND or a transient wrong-PID witness.
    """
    actual_pid = wintypes.DWORD(0)
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(actual_pid))
    if (not thread_id or actual_pid.value != pid or
            not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or
            user32.GetWindow(hwnd, _GW_OWNER)):
        return False
    klass = ctypes.create_unicode_buffer(260)
    length = user32.GetClassNameW(hwnd, klass, len(klass))
    return (type(length) is int and 0 < length < len(klass) and
            klass.value.startswith(_WPF_CLASS_PREFIX))


def _visible_window_for_pid(pid: int, user32: object, callback_type: object) -> int | None:
    """Isolated Win32 enumeration, accepting no HWND from a different PID."""
    if type(pid) is not int or pid <= 0:
        return None
    matches: list[int] = []

    def inspect(hwnd: int, _lparam: int) -> bool:
        if _same_live_wpf_window(hwnd, pid, user32):
            matches.append(int(hwnd))
        # Continue: the first WPF splash can vanish before final PID/class proof.
        return True

    callback = callback_type(inspect)  # retain callback throughout EnumWindows
    # A failed/partial Win32 enumeration cannot certify a live GUI.
    if not user32.EnumWindows(callback, 0):
        return None
    for hwnd in matches:
        if _same_live_wpf_window(hwnd, pid, user32):
            return hwnd
    return None


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
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        return _visible_window_for_pid(pid, user32, callback_type)
    except (AttributeError, OSError, TypeError, ValueError):
        return None
