"""Exact old Drive bridge with one verified cold builder exception.

Call run_envelope for subsequent transfers after the cold transition.  The
frozen old bridge and its RAM receipts remain unchanged.  This wrapper writes
separate mixed-storage receipts and never downloads over the builder alias.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import time

SCRIPTS = Path('/root/nox/scripts')
BRIDGE_SHA = '57893b187155b12c08b3ca0612a62397d117218302d448994a346c84f556b786'
LOCATION_SHA = 'f573a7c5509786139b80768bc009fcbbae89c1a088e3d81361aa0d9eb7dbd965'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_DRIVE_STORAGE_' + code)


def module(name, expected):
    path = SCRIPTS / (name + '.py')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 < before.st_size <= 65536, 'SOURCE_SCOPE')
        raw = os.pread(fd, 65537, 0)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(raw) == before.st_size and hashlib.sha256(raw).hexdigest() == expected
                and all(getattr(before, k) == getattr(os.fstat(fd), k) == getattr(path.lstat(), k) for k in keys), 'SOURCE_PIN')
    finally:
        os.close(fd)
    value = importlib.util.module_from_spec(importlib.util.spec_from_loader('_pinned_' + name, loader=None))
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value, raw


def exact_asset(asset, location):
    require(isinstance(asset, dict) and asset.get('role') == 'builder'
            and asset.get('filename') == location.ALIAS.name and asset.get('bytes') == location.SIZE
            and asset.get('sha256') == location.SHA, 'BUILDER_ASSET')


def compose_consume(raw):
    tree = ast.parse(raw)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'consume']
    require(len(nodes) == 1 and hashlib.sha256(raw).hexdigest() == BRIDGE_SHA, 'CONSUME_SOURCE_PIN')
    text = ast.get_source_segment(raw.decode(), nodes[0]) + '\n'
    edits = (
        ("STATE / 'consumed'", "STATE / 'storage_consumed'", 2),
        ("'NOX_DRIVE_RAM_RECEIPT_V1'", "'NOX_DRIVE_STORAGE_RECEIPT_V1'", 1),
        ("'RAM_FILES_SHA_VERIFIED_NOT_MERGED'", "'MIXED_STORAGE_FILES_SHA_VERIFIED_NOT_MERGED'", 2),
        ("receipt['destination'] = str(DESTINATION)", "receipt['destination'] = 'TWO_RAM_AND_ONE_COLD_SSD'", 1),
        ("STATE / 'latest_receipt.json'", "STATE / 'latest_storage_receipt.json'", 1),
        ("    helper = load_prepare()", "    cold = _cold_location.locate(rehash=True, deadline=time.monotonic()+30)\n    helper = load_prepare()", 1),
        ("    with helper.state_lock('transfer.lock'):",
         "    with helper.state_lock('transfer.lock'):\n"
         "        old_receipt_path = plain(STATE / 'consumed' / (envelope_sha + '.json'))\n"
         "        if old_receipt_path.exists():\n            fail('HOLD_DRIVE_ENVELOPE_ALREADY_CONSUMED')", 1),
        ("        helper.atomic_private(receipt_path, canonical(receipt) + b'\\n')",
         "        receipt['builder_storage_receipt_sha256'] = cold['receipt_sha256']\n"
         "        receipt['ram_files'] = 2\n        receipt['cold_ssd_files'] = 1\n"
         "        helper.atomic_private(receipt_path, canonical(receipt) + b'\\n')", 1),
    )
    # The last old snippet occurs also at deeper indentation; exact lines keep
    # only initial receipt creation in scope.
    for old, new, count in edits:
        if old.startswith('        helper.atomic_private'):
            lines = text.splitlines(keepends=True)
            require(sum(line.rstrip('\n') == old for line in lines) == count, 'CONSUME_ANCHOR')
            text = ''.join(new + '\n' if line.rstrip('\n') == old else line for line in lines)
        else:
            require(text.count(old) == count, 'CONSUME_ANCHOR')
            text = text.replace(old, new)
    compile(text, '<exact-drive-storage-consume>', 'exec')
    return text


def bind(bridge, raw, location):
    old_remaining = bridge.remaining_bytes; old_transfer = bridge.transfer_asset

    def remaining(manifest):
        location.locate()
        rows = manifest.get('assets', [])
        builders = [a for a in rows if a.get('role') == 'builder']
        require(len(builders) == 1, 'MANIFEST_BUILDER'); exact_asset(builders[0], location)
        return old_remaining({**manifest, 'assets': [a for a in rows if a.get('role') != 'builder']})

    def transfer(asset, links, manifest, helper, deadline):
        if asset.get('role') != 'builder':
            return {**old_transfer(asset, links, manifest, helper, deadline), 'storage': 'RAM', 'ram_resident': True}
        exact_asset(asset, location)
        value = location.locate(rehash=True, deadline=deadline)
        info = value['canonical_identity']
        return {'role': 'builder', 'filename': location.ALIAS.name, 'bytes': location.SIZE,
                'sha256': location.SHA, 'verified': True, 'reused': True, 'storage': 'SSD',
                'location_state': 'COLD_ON_SSD', 'ram_resident': False, 'automatic_ram_restage': False,
                'stat_inode': info['st_ino'], 'stat_device': info['st_dev'], 'stat_mtime_ns': info['st_mtime_ns'],
                'storage_receipt_sha256': value['receipt_sha256']}

    bridge.remaining_bytes = remaining; bridge.transfer_asset = transfer
    bridge.__dict__['_cold_location'] = location
    exec(compile(compose_consume(raw), '<exact-drive-storage-consume>', 'exec'), bridge.__dict__)
    return bridge


def run_envelope(envelope):
    location, _ = module('owner_builder_cold_location', LOCATION_SHA)
    bridge, raw = module('owner_drive_ram_bridge', BRIDGE_SHA)
    return bind(bridge, raw, location).run_envelope(envelope)
