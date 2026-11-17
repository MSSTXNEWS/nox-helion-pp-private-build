#!/usr/bin/env python3
"""Standalone, source-pinned UI repair. Default: read-only check. No HTTP/restart."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

SITE = '/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
MAINTENANCE_LOCK = '/root/nox/state/owner_maintenance.lock'
BEFORE_SHA = '9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194'
AFTER_SHA = '597ede7cf68e7606fc6b761f7d366e14737f86ffa50d648b637857b2275d070b'
# Generated from the separately reviewable pc/ assets; no runtime dependencies.
ASSETS = {'nox-resonance-native-fix-v1.css': '/* Native Resonance compatibility fix. Existing theme and handlers stay in place. */\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .v24-top,\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .nox-shared-header-v10 {\n  color: #fff2db !important;\n  background: linear-gradient(150deg, #26313d, #151c25) !important;\n  border-color: #b48b52 !important;\n}\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .v24-brand,\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .v24-top button,\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .nox-shared-links-v10 a,\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .nox-shared-catalog-v11 {\n  color: #fff2db !important;\n}\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .v24-new[data-action="new-chat"] {\n  color: #fff2db !important;\n  background: linear-gradient(150deg, #49351e, #2c2117) !important;\n  border-color: #e3b36a !important;\n  font-weight: 700;\n}\nhtml body[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] .v24-new:focus-visible {\n  outline: 2px solid #ffe0a3 !important;\n  outline-offset: 3px;\n}\nbody[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] #messages {\n  color: #fff2db;\n  line-height: 1.55;\n  min-height: 0;\n  overflow-wrap: anywhere;\n  scroll-padding-block-start: 12px;\n}\nbody[data-nox-view="resonance-v24"][data-nox-layout-inset="ready"] #messages {\n  margin-block-start: calc(var(--nox-message-base-margin, 0px) + var(--nox-message-header-inset, 0px)) !important;\n}\nbody[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] #prompt {\n  color: #fff2db !important;\n  line-height: 1.45;\n}\nbody[data-nox-view="resonance-v24"][data-nox-readability-fix="1"] #nox-public-safe-preview {\n  color: #fff2db !important;\n  background: #151c25 !important;\n  border-color: #b48b52 !important;\n  max-width: calc(100vw - 24px);\n  overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n  pointer-events: none;\n}\n', 'nox-resonance-native-fix-v1.js': "/* Read-only DOM compatibility. No network, model calls, storage or chat handlers. */\n(function (root) {\n  'use strict';\n  function insetFor(top, previousExtra, headerBottom, limit) {\n    if (![top, previousExtra, headerBottom, limit].every(Number.isFinite)) return 0;\n    return Math.min(Math.max(0, limit), Math.max(0, Math.ceil(headerBottom + 12 - (top - previousExtra))));\n  }\n  function pageLabel(location) {\n    if (!location || !/^https?:$/.test(location.protocol)) return 'NOX HELION · Резонанс';\n    const host = typeof location.host === 'string' ? location.host.replace(/[\\u0000-\\u001f\\u007f]/g, '').trim().slice(0, 180) : '';\n    return host ? 'NOX HELION · ' + host : 'NOX HELION · Резонанс';\n  }\n  if (typeof module === 'object' && module.exports) module.exports = {insetFor, pageLabel};\n  if (!root.document) return;\n  function start() {\n    const document = root.document, body = document.body;\n    if (!body || body.dataset.noxView !== 'resonance-v24' || body.dataset.noxReadabilityFix !== '1') return;\n    const badge = document.getElementById('nox-public-safe-preview');\n    if (badge) {\n      badge.textContent = pageLabel(root.location);\n      badge.title = 'Адрес открытой страницы';\n    }\n    const messages = document.getElementById('messages');\n    if (!messages) return;\n    const computed = root.getComputedStyle(messages);\n    const base = parseFloat(computed.marginBlockStart || computed.marginTop) || 0;\n    body.style.setProperty('--nox-message-base-margin', base + 'px');\n    body.dataset.noxLayoutInset = 'ready';\n    let extra = 0, frame = 0, disposed = false;\n    const headers = Array.from(document.querySelectorAll('.nox-v28-pc-return, .nox-shared-header-v10, .v24-top'));\n    function measure() {\n      frame = 0;\n      if (disposed || document.hidden) return;\n      const box = messages.getBoundingClientRect();\n      if (box.width <= 0 || box.height <= 0) return;\n      let bottom = 0;\n      for (const header of headers) {\n        const rect = header.getBoundingClientRect();\n        if (rect.width > 0 && rect.height > 0 && rect.right > box.left && rect.left < box.right) bottom = Math.max(bottom, rect.bottom);\n      }\n      const limit = Math.min(320, Math.max(0, root.innerHeight * 0.4));\n      const next = insetFor(box.top, extra, bottom, limit);\n      body.dataset.noxInsetState = next >= limit && bottom + 12 - (box.top - extra) > limit ? 'needs-layout-review' : 'measured';\n      if (Math.abs(next - extra) >= 1) {\n        extra = next;\n        body.style.setProperty('--nox-message-header-inset', next + 'px');\n      }\n    }\n    function schedule() { if (!frame && !disposed) frame = root.requestAnimationFrame(measure); }\n    const observer = typeof root.ResizeObserver === 'function' ? new root.ResizeObserver(schedule) : null;\n    if (observer) { headers.forEach(element => observer.observe(element)); observer.observe(messages); }\n    root.addEventListener('resize', schedule, {passive: true});\n    root.addEventListener('pageshow', schedule);\n    document.addEventListener('visibilitychange', schedule);\n    if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);\n    schedule();\n    function onPageHide(event) {\n      if (event.persisted) return; // BFCache freezes this document; keep its observers for restore.\n      disposed = true;\n      if (frame) root.cancelAnimationFrame(frame);\n      if (observer) observer.disconnect();\n      root.removeEventListener('resize', schedule);\n      root.removeEventListener('pageshow', schedule);\n      root.removeEventListener('pagehide', onPageHide);\n      document.removeEventListener('visibilitychange', schedule);\n    }\n    root.addEventListener('pagehide', onPageHide);\n  }\n  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start, {once: true});\n  else start();\n})(typeof window === 'object' ? window : globalThis);\n"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise ValueError('HOLD: unexpected file type/size: ' + str(path))
        return handle.read(), stat.S_IMODE(info.st_mode)


def transform(data):
    if digest(data) != BEFORE_SHA:
        raise ValueError('HOLD: native HTML SHA differs')
    text = data.decode('utf-8')
    edits = [
        ('</head>', '<link rel="stylesheet" href="./nox-resonance-native-fix-v1.css" data-nox-native-fix="1">\n</head>'),
        ('data-nox-phase="idle">', 'data-nox-phase="idle" data-nox-readability-fix="1">'),
        ('LOCAL · NOX HELION V25 · 127.0.0.1', 'NOX HELION · Резонанс'),
        ('</body>', '<script defer src="./nox-resonance-native-fix-v1.js" data-nox-native-fix="1"></script>\n</body>'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError('HOLD: patch anchor count differs')
        text = text.replace(old, new, 1)
    result = text.encode('utf-8')
    if digest(result) != AFTER_SHA:
        raise ValueError('HOLD: generated HTML SHA differs')
    return result


def sync_directory(path):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def atomic_write(path, data, mode, *, no_clobber=False):
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if no_clobber:
            try:
                # Same-directory hard link publishes complete bytes only if absent.
                os.link(tmp, path, follow_symlinks=False)
            except FileExistsError:
                if read_regular(path)[0] != data:
                    raise ValueError('HOLD: late asset collision: ' + path.name)
        else:
            os.replace(tmp, path)
        sync_directory(path.parent)
        if read_regular(path)[0] != data:
            raise ValueError('HOLD: write readback differs')
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(action='check', site_dir=SITE, *, maintenance_lock_fd=None, maintenance_lock_path=MAINTENANCE_LOCK):
    site = Path(site_dir).absolute()
    pc = site / 'pc'
    if site.is_symlink() or pc.is_symlink():
        raise ValueError('HOLD: site/pc is a symlink')
    target = pc / 'resonance.html'
    backup = pc / ('.resonance-before-native-fix-' + BEFORE_SHA[:16] + '.bak')

    def operate():
        current, mode = read_regular(target)
        current_sha = digest(current)
        receipt = {'action': action, 'target': str(target), 'before_sha256': BEFORE_SHA,
                   'after_sha256': AFTER_SHA, 'observed_sha256': current_sha,
                   'backup': str(backup), 'network_calls': 0, 'service_restarts': 0,
                   'native_ui_verified': False,
                   'serialization': 'existing owner_maintenance.lock + local patch lock; cooperating writers only'}
        if action == 'rollback':
            if current_sha == BEFORE_SHA:
                return dict(receipt, status='ALREADY_ORIGINAL')
            if current_sha != AFTER_SHA:
                raise ValueError('HOLD: rollback refuses changed HTML')
            original, _ = read_regular(backup)
            if digest(original) != BEFORE_SHA:
                raise ValueError('HOLD: backup SHA differs')
            if read_regular(target)[0] != current:
                raise ValueError('HOLD: HTML changed before rollback')
            atomic_write(target, original, mode)
            return dict(receipt, status='ROLLED_BACK', observed_sha256=BEFORE_SHA,
                        assets_retained_unreferenced=True)
        if current_sha not in (BEFORE_SHA, AFTER_SHA):
            raise ValueError('HOLD: native HTML SHA differs')
        missing = []
        for name, text in ASSETS.items():
            path = pc / name
            if path.exists() or path.is_symlink():
                if read_regular(path)[0] != text.encode('utf-8'):
                    raise ValueError('HOLD: asset collision: ' + name)
            else:
                missing.append(name)
        if current_sha == AFTER_SHA:
            if missing:
                raise ValueError('HOLD: applied HTML has missing assets')
            original, _ = read_regular(backup)
            if digest(original) != BEFORE_SHA:
                raise ValueError('HOLD: applied HTML has invalid backup')
            return dict(receipt, status='ALREADY_APPLIED')
        updated = transform(current)
        if backup.exists() or backup.is_symlink():
            if read_regular(backup)[0] != current:
                raise ValueError('HOLD: backup collision')
        if action == 'check':
            return dict(receipt, status='READY', missing_assets=missing)
        if action != 'apply':
            raise ValueError('HOLD: unknown action')
        if not backup.exists():
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(current)
                handle.flush()
                os.fsync(handle.fileno())
        if read_regular(backup)[0] != current:
            raise ValueError('HOLD: backup readback differs')
        sync_directory(pc)
        for name in missing:
            atomic_write(pc / name, ASSETS[name].encode('utf-8'), 0o644, no_clobber=True)
        # Maintenance lock covers cooperating native writers, not unrelated editors.
        if read_regular(target)[0] != current:
            raise ValueError('HOLD: HTML changed before commit; unused assets may remain')
        atomic_write(target, updated, mode)
        return dict(receipt, status='APPLIED', observed_sha256=AFTER_SHA)

    if action == 'check':
        return operate()
    owns_maintenance_fd = maintenance_lock_fd is None
    maintenance = os.open(maintenance_lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600) if owns_maintenance_fd else maintenance_lock_fd
    try:
        actual, expected = os.fstat(maintenance), os.lstat(maintenance_lock_path)
        if not stat.S_ISREG(actual.st_mode) or not stat.S_ISREG(expected.st_mode) or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError('HOLD: maintenance FD does not match the native lock file')
        # An already-held FD may be passed by owner_native_repair. Never unlock/close it.
        fcntl.flock(maintenance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock = os.open(pc / '.nox-native-ui-patch.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return operate()
        finally:
            os.close(lock)
    finally:
        if owns_maintenance_fd:
            os.close(maintenance)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-dir', default=SITE, help='Existing site root; fixture override for local tests')
    parser.add_argument('--maintenance-lock-fd', type=int, help='Already-held native maintenance FD, inherited explicitly from owner repair')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    try:
        result = run('apply' if args.apply else 'rollback' if args.rollback else 'check', args.site_dir, maintenance_lock_fd=args.maintenance_lock_fd)
    except (OSError, ValueError) as exc:
        print('NOX_RESONANCE_PATCH=' + json.dumps({'status': 'HOLD', 'reason': str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
    print('NOX_RESONANCE_PATCH=' + json.dumps(result, ensure_ascii=False, sort_keys=True))
