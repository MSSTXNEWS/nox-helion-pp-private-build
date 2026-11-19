#!/usr/bin/env python3
"""Source-pinned one-turn entry for frozen 1A01 UI-state evidence.

This file is not registered in the native operator, a workflow, or a dispatcher.
It exists as an owner-run source candidate; its core SHA is fixed below so an
unreviewed runner cannot silently replace the bounded browser checks.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import runpy
import shutil

CORE = Path(__file__).with_name('owner_chat_browser_qa.py')
CORE_SHA256 = '4b15b3b3d3ae227663c8eb0bb8404b3550c205fede9b36baf1381d660582c126'
ROOT = Path('/root/nox')


def stop_present():
    paths = [ROOT / name for name in
             ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def resource_gate():
    if stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')
    if shutil.disk_usage(ROOT).free < 7 * 1024 ** 3:
        raise RuntimeError('HOLD_DISK_RESERVE')
    try:
        maximum = (Path('/sys/fs/cgroup') / 'memory.max').read_text().strip()
        current = (Path('/sys/fs/cgroup') / 'memory.current').read_text().strip()
    except OSError:
        raise RuntimeError('HOLD_RAM_UNKNOWN') from None
    if not maximum.isdigit() or not current.isdigit():
        raise RuntimeError('HOLD_RAM_UNKNOWN')
    if int(maximum) - int(current) < 4 * 1024 ** 3:
        raise RuntimeError('HOLD_RAM_RESERVE')
    if stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')


def main():
    try:
        raw = CORE.read_bytes()
    except OSError:
        raise RuntimeError('HOLD_ORIGINAL_CARD_CORE_MISSING') from None
    if hashlib.sha256(raw).hexdigest() != CORE_SHA256:
        raise RuntimeError('HOLD_ORIGINAL_CARD_CORE_PIN')
    if not re.fullmatch(r'[0-9]{1,24}', os.environ.get('NOX_OWNER_REQUEST_ID', '')):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    if not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    resource_gate()
    os.environ['NOX_BROWSER_QA_MODE'] = 'original_card'
    namespace = runpy.run_path(str(CORE), run_name='nox_original_card_core')
    return namespace['main']()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        text = str(exc)
        if not re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', text):
            text = type(exc).__name__
        print('NOX_1A01_ORIGINAL_CARD_HOLD=' + text, flush=True)
        raise SystemExit(2)
