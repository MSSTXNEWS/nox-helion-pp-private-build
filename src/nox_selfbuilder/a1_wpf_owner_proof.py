"""NOX A.1: verify one ephemeral consent receipt issued inside original WPF.

The child process inherits the key through its private process environment, never
from WebView JSON, a downloaded file, or the user configuration. This proof
attests WPF routing only; it is NOT FirstBoot download permission, a signed
research policy, or a replacement for native STOP, source HEAD, ACL or E07.
"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
from pathlib import Path
import re
import sys
import time

_HEX64 = re.compile(r'[a-f0-9]{64}\Z')
_NONCE = re.compile(r'[a-f0-9]{32}\Z')
_RUNID = re.compile(r'[ -~]{1,128}\Z')
_ACTIONS = frozenset({'selfbuilder.a1.boot', 'selfbuilder.a1.tick'})
_SCHEMA = 'NOX-A1-WPF-OWNER-CONSENT-v1'
_FIELDS = frozenset({'schema', 'run_id', 'action', 'backend_sha256',
                     'sid_sha256', 'native_stop_epoch', 'nonce', 'issued_unix', 'expires_unix', 'mac'})


class A1OwnerProofHold(PermissionError):
    pass


def _windows_sid():
    """Read SID from OS access token, not a page-supplied identity string."""
    if sys.platform != 'win32':
        raise A1OwnerProofHold('A1_NATIVE_WINDOWS_SID_REQUIRED')
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                               ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise A1OwnerProofHold('A1_NATIVE_WINDOWS_TOKEN_HOLD')
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        if not 8 <= needed.value <= 4096:
            raise A1OwnerProofHold('A1_NATIVE_WINDOWS_TOKEN_SIZE_HOLD')
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, buf, needed.value, ctypes.byref(needed)):
            raise A1OwnerProofHold('A1_NATIVE_WINDOWS_TOKEN_READ_HOLD')
        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first member is SID pointer.
        sid_pointer = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_text = wintypes.LPWSTR()
        if not sid_pointer or not advapi.ConvertSidToStringSidW(
                sid_pointer, ctypes.byref(sid_text)):
            raise A1OwnerProofHold('A1_NATIVE_WINDOWS_SID_CONVERSION_HOLD')
        try:
            value = sid_text.value
        finally:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if not isinstance(value, str) or not value.startswith('S-1-'):
            raise A1OwnerProofHold('A1_NATIVE_WINDOWS_SID_INVALID')
        return value
    finally:
        kernel.CloseHandle(token)


def _digest_file(path):
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise A1OwnerProofHold('A1_BACKEND_BINARY_UNAVAILABLE')
    digest = hashlib.sha256()
    with target.open('rb') as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def transcript(value):
    """ASCII message, exactly mirrored by original WPF owner HMACSHA256."""
    return '\n'.join((value['schema'], value['run_id'], value['action'],
                      value['backend_sha256'], value['sid_sha256'],
                      str(value['native_stop_epoch']), str(value['issued_unix']), str(value['expires_unix']),
                      value['nonce'])).encode('ascii')


class A1WpfOwnerProof:
    def __init__(self, secret_hex, run_id, backend_binary, *, sid_provider=None,
                 clock=None, stop_epoch=None):
        if type(secret_hex) is not str or not _HEX64.fullmatch(secret_hex):
            raise A1OwnerProofHold('A1_EPHEMERAL_OWNER_KEY_REQUIRED')
        if type(run_id) is not str or not _RUNID.fullmatch(run_id):
            raise A1OwnerProofHold('A1_ORIGINAL_NATIVE_RUNID_REQUIRED')
        self._secret = bytes.fromhex(secret_hex)
        self._run_id = run_id
        self._backend_sha = _digest_file(backend_binary)
        self._sid = sid_provider or _windows_sid
        self._clock = clock or time.time
        self._seen = set()
        self._stop_epoch = None
        if stop_epoch is not None:
            self.bind_stop_epoch(stop_epoch)

    def bind_stop_epoch(self, callback):
        # Bind ONCE from the original OneHost runtime after P02 is created.
        # No browser payload, model or S03 record may supply this callback.
        if self._stop_epoch is not None or not callable(callback):
            raise A1OwnerProofHold('A1_NATIVE_STOP_EPOCH_BINDING_REQUIRED')
        self._stop_epoch = callback

    @classmethod
    def from_native_child(cls, run_id, backend_binary):
        # One-shot consumption; do not allow spawned models/tools to inherit it.
        secret = os.environ.pop('NOX_A1_WPF_OWNER_KEY', None)
        return cls(secret, run_id, backend_binary)

    def verify(self, ticket, action):
        if action not in _ACTIONS or type(ticket) is not dict or set(ticket) != _FIELDS:
            raise A1OwnerProofHold('A1_WPF_EXACT_OWNER_RECEIPT_REQUIRED')
        if (ticket['schema'] != _SCHEMA or ticket['run_id'] != self._run_id or
                ticket['action'] != action or
                ticket['backend_sha256'] != self._backend_sha or
                type(ticket['nonce']) is not str or
                not _NONCE.fullmatch(ticket['nonce']) or
                type(ticket['mac']) is not str or not _HEX64.fullmatch(ticket['mac'])):
            raise A1OwnerProofHold('A1_WPF_OWNER_BINDING_MISMATCH')
        if (type(ticket['issued_unix']) is not int or
                type(ticket['expires_unix']) is not int or
                ticket['expires_unix'] - ticket['issued_unix'] != 20):
            raise A1OwnerProofHold('A1_WPF_OWNER_EXPIRY_HOLD')
        # Native STOP epoch must match the WPF epoch; a late pre-STOP
        # consent must not become valid after stop/reset within one process.
        if self._stop_epoch is None or type(ticket['native_stop_epoch']) is not int:
            raise A1OwnerProofHold('A1_NATIVE_STOP_EPOCH_REQUIRED')
        try:
            current_epoch = self._stop_epoch()
        except Exception as exc:
            raise A1OwnerProofHold('A1_NATIVE_STOP_EPOCH_UNAVAILABLE') from exc
        if (type(current_epoch) is not int or current_epoch < 0 or
                ticket['native_stop_epoch'] != current_epoch):
            raise A1OwnerProofHold('A1_STOP_EPOCH_REVOKED')
        now = int(self._clock())
        if not ticket['issued_unix'] - 5 <= now <= ticket['expires_unix']:
            raise A1OwnerProofHold('A1_WPF_OWNER_EXPIRED_OR_CLOCK_HOLD')
        sid = self._sid()
        if (type(sid) is not str or not sid.startswith('S-1-') or
                ticket['sid_sha256'] != hashlib.sha256(sid.encode('utf-8')).hexdigest()):
            raise A1OwnerProofHold('A1_WPF_WINDOWS_SID_MISMATCH')
        try:
            expected = hmac.new(self._secret, transcript(ticket), hashlib.sha256).hexdigest()
        except (KeyError, TypeError, UnicodeError, ValueError):
            raise A1OwnerProofHold('A1_WPF_OWNER_RECEIPT_INVALID') from None
        if not hmac.compare_digest(expected, ticket['mac']):
            raise A1OwnerProofHold('A1_WPF_OWNER_MAC_INVALID')
        nonce = ticket['nonce']
        if nonce in self._seen or len(self._seen) >= 8192:
            raise A1OwnerProofHold('A1_WPF_OWNER_NONCE_REPLAY')
        self._seen.add(nonce)
        return True
