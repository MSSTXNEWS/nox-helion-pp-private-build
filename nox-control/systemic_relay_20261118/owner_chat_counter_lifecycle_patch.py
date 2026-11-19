#!/usr/bin/env python3
"""Exact-source chat inflight accounting fixes; pure source transform ONLY.

Do not run this code on a live process or modify chat_state.json. The serving
source should only be installed under owner lease, quiescence and rollback
checks. A historical inflated counter must never be silently reset here.
"""
from __future__ import annotations
import ast
import hashlib
import re

SOURCE_PINS = {
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
    'chat_proxy.py': '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
}
SYMBOL_PINS = {
    'common.py': ('mark_chat', '156f8727e714a5864a10d34cfbdf6a97f78703c9f81893b49cb4ea21676c49ec'),
    'chat_proxy.py': ('_ChatActivityStream', '12f8ccd256246c68d78caae05d0ce54ad90cc8803515f3ebc2f804b518defc57'),
}
MARK_START = '    st = load_json(CHAT_STATE, {}) or {}\n'
MARK_END = '    atomic_write_json(CHAT_STATE, st)'
CLOSE_OLD = (
    "        if hasattr(self._iterator, 'aclose'):\n"
    "            await self._iterator.aclose()\n"
    "        # Release only after the owned pull and close have finished. A failed\n"
    "        # close leaves the count acquired and prohibits further reads.\n"
    "        self._closed = True\n"
    "        self._release()"
)


class Hold(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def patch(name: str, raw: bytes, expected_file_sha256: str | None = None,
          expected_symbol_sha256: str | None = None) -> bytes:
    if name not in SOURCE_PINS or not isinstance(raw, bytes) or not 0 < len(raw) <= 262144:
        raise Hold('HOLD_COUNTER_SOURCE_SCOPE')
    if expected_file_sha256 is None:
        expected_file_sha256 = SOURCE_PINS[name]
    if expected_symbol_sha256 is None:
        expected_symbol_sha256 = SYMBOL_PINS[name][1]
    if (not re.fullmatch(r'[a-f0-9]{64}', expected_file_sha256 or '')
            or digest(raw) != expected_file_sha256):
        raise Hold('HOLD_COUNTER_FILE_PIN')
    source = raw.decode('utf-8')
    tree = ast.parse(source)
    symbol = SYMBOL_PINS[name][0]
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and node.name == symbol]
    if len(nodes) != 1:
        raise Hold('HOLD_COUNTER_SYMBOL_COUNT')
    old = ast.get_source_segment(source, nodes[0])
    if old is None or digest((old + '\n').encode()) != expected_symbol_sha256:
        raise Hold('HOLD_COUNTER_SYMBOL_PIN')

    if name == 'common.py':
        if old.count(MARK_START) != 1 or old.count(MARK_END) != 1:
            raise Hold('HOLD_COUNTER_MARK_ANCHOR')
        old_middle = old[old.index(MARK_START):old.index(MARK_END) + len(MARK_END)]
        replacement = '''    import fcntl as _chat_fcntl
    import os as _chat_os
    import stat as _chat_stat
    guard = CHAT_STATE.with_name(CHAT_STATE.name + '.writer.lock')
    fd = _chat_os.open(guard, _chat_os.O_RDWR | _chat_os.O_CREAT |
                       _chat_os.O_NOFOLLOW | _chat_os.O_CLOEXEC, 0o600)
    try:
        info = _chat_os.fstat(fd)
        if (not _chat_stat.S_ISREG(info.st_mode) or info.st_uid != _chat_os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise RuntimeError('HOLD_CHAT_COUNTER_LOCK_IDENTITY')
        _chat_fcntl.flock(fd, _chat_fcntl.LOCK_EX)
        st = load_json(CHAT_STATE, {}) or {}
        now = time.time()
        if busy:
            st["inflight"] = int(st.get("inflight", 0)) + 1
            st["last_start"] = now
        else:
            st["inflight"] = max(0, int(st.get("inflight", 0)) - 1)
            st["last_end"] = now
        st["last_ts"] = now
        if extra:
            st.update(extra)
        atomic_write_json(CHAT_STATE, st)
    finally:
        _chat_os.close(fd)'''
        newer = old.replace(old_middle, replacement, 1)
    else:
        if old.count(CLOSE_OLD) != 1:
            raise Hold('HOLD_COUNTER_CLOSE_ANCHOR')
        newer = old.replace(
            CLOSE_OLD,
            "        # After the pending pull settles, an iterator close error must\n"
            "        # not leak this request's activity count.\n"
            "        try:\n"
            "            if hasattr(self._iterator, 'aclose'):\n"
            "                await self._iterator.aclose()\n"
            "        finally:\n"
            "            self._closed = True\n"
            "            self._release()",
            1)
    if source.count(old) != 1 or newer == old:
        raise Hold('HOLD_COUNTER_REPLACEMENT')
    candidate = source.replace(old, newer, 1).encode('utf-8')
    new_tree = ast.parse(candidate)
    if len(new_tree.body) != len(tree.body):
        raise Hold('HOLD_COUNTER_UNRELATED_AST')
    for first, second in zip(tree.body, new_tree.body):
        if first is nodes[0]:
            continue
        if ast.dump(first, include_attributes=False) != ast.dump(second, include_attributes=False):
            raise Hold('HOLD_COUNTER_UNRELATED_AST')
    return candidate
