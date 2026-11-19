#!/usr/bin/env python3
"""Owner transaction for the one hash-pinned WOW menu script on native V29."""

import base64
from contextlib import ExitStack
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types
from zipfile import ZipFile

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
INCOMING = ROOT / 'incoming_t800u/wow_r62_owner_private/NOX_WOW_R6_2_NATIVE_MENU_ONLY.zip'
BACKUP = ROOT / 'backup'
WRITE_LOCK = ROOT / 'state/owner_wow_r62_static.lock'
ZIP_SHA = '6eddd41d275e8a09bf5c32c02f5504353bfabca7b7af164ef7404f1ddf2379b2'
ZIP_BYTES = 5460
MATRIX = 'owner_wow_served_asset_receipt.py'
EXCHANGE = 'owner_chat_stream_asset_install_v2.py'
AUTH = 'owner_media_acceptance_entry.py'
SOURCE_PINS = {
    MATRIX: 'a60bd596124507bbf8f3b1d91e2ff3d4699bb184dda206900431648655b90fe3',
    EXCHANGE: 'f3b1bddf2f53e57f671774e76d6bc7d64f59e6f0a0a9642a34714643323a89fa',
    AUTH: '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60',
}
TARGETS = ('pc/v24/nox-v24-menu.js',)
HEX = re.compile(r'[0-9a-f]{64}')
SAFE_ERROR = re.compile(r'(?:WAIT|HOLD)_[A-Z0-9_]{1,120}')


def require(ok, reason):
    if not ok:
        raise RuntimeError('HOLD_WOW_APPLY_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(exc):
    message = str(exc)
    if SAFE_ERROR.fullmatch(message):
        return message
    return 'HOLD_WOW_APPLY_' + type(exc).__name__.upper()


def modules():
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == set(SOURCE_PINS), 'SOURCE_BUNDLE')
    loaded = {}
    for name, pin in SOURCE_PINS.items():
        encoded = BUNDLE[name]
        require(isinstance(encoded, str) and 0 < len(encoded) <= 500000, 'SOURCE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 262144 and sha(raw) == pin, 'SOURCE_PIN')
        if name != AUTH:
            module = types.ModuleType('nox_wow_release_' + name[:-3])
            exec(compile(raw, name, 'exec'), module.__dict__)
            loaded[name] = module
    matrix, engine = loaded[MATRIX], loaded[EXCHANGE]
    matrix.BUNDLE = {AUTH: BUNDLE[AUTH]}
    return matrix, engine, matrix.load_auth()


def payload(engine):
    parent_fd = engine.directory(INCOMING.parent)
    try:
        raw, _ = engine.read_at(parent_fd, INCOMING.name, ZIP_BYTES, expected=ZIP_SHA, private=True)
    finally:
        os.close(parent_fd)
    require(len(raw) == ZIP_BYTES, 'ZIP_SIZE')
    with ZipFile(BytesIO(raw)) as archive:
        allowed = {'MANIFEST.json', *('payload/' + name for name in TARGETS)}
        entries = archive.infolist()
        require(len(entries) == len(allowed) and {item.filename for item in entries} == allowed
                and all(0 < item.file_size <= 32768 for item in entries), 'ZIP_SCOPE')
        manifest = json.loads(archive.read('MANIFEST.json'))
        require(manifest.get('schema') == 'NOX_WOW_R6_2_NATIVE_MENU_ONLY_SOURCE_V1'
                and manifest.get('mount') == '/nox-web-v29/'
                and [row['path'] for row in manifest['files']] == list(TARGETS)
                and manifest['required_no_write_dependencies'] == [],
                'MANIFEST_SCOPE')
        files = {}
        for row in manifest['files']:
            name = row['path']
            value = archive.read('payload/' + name)
            require(HEX.fullmatch(row['conditional_before_sha256'])
                    and len(value) == row['after_bytes'] and sha(value) == row['after_sha256'],
                    'PAYLOAD_PIN')
            files[name] = (row, value)
    return files


def check_stop(signum, _frame):
    raise RuntimeError('HOLD_WOW_APPLY_SIGNAL_' + str(signum))


def projected(raw, info):
    return {'sha256': sha(raw), 'bytes': len(raw), 'inode': info['inode'], 'device': info['device']}


def verify_lease(fd, path):
    opened = os.fstat(fd)
    named = path.lstat()
    require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'LEASE_REPLACED')


def live_read(matrix, engine, row, cookie):
    engine.named_directory(row['directory'], row['site_fd'])
    raw, info = engine.read_at(row['site_fd'], row['basename'])
    status, http = matrix.served(row['relative'], cookie)
    repeated, after = engine.read_at(row['site_fd'], row['basename'])
    require(raw == repeated and info == after, 'CAS_RACED_READ')
    require(status == 200 and http == (len(raw), sha(raw)), 'HTTP_DISK_MISMATCH')
    return raw, info


def protected(matrix, auth, cookie):
    values = {}
    for name in matrix.REQUIRED:
        # The active proxy injects the Resonance document and serves V135/V137
        # compatibility shims directly. Capture both views as observed and
        # require exact stability across this same-session menu-only operation.
        row, _ = matrix.asset_row(name, auth, cookie)
        require(row['http'] == 200 and HEX.fullmatch(row.get('served_sha256', '')), 'NATIVE_CHAT_PREIMAGE')
        values[name] = row
    return values


def switch_names(engine, row):
    engine.ASSET = row['basename']
    engine.OLD_SHA = row['expected_before']
    engine.NEW_SHA = row['expected_after']


def rollback(matrix, engine, rows, record, client):
    record['rollback_requested'] = bool(rows)
    complete = True
    for row in reversed(rows):
        output = row['receipt']
        try:
            switch_names(engine, row)
            engine.named_directory(row['directory'], row['site_fd'])
            engine.named_directory(row['backup_path'], row['backup_fd'])
            require(engine.restore_owned(row['site_fd'], row['backup_fd'], row['pair']), 'ROLLBACK_DISK')
            output['state'] = 'RESTORED_EXACT_DISK'
        except BaseException as exc:
            complete = False
            output.update(state='ROLLBACK_HELD', rollback_reason=safe(exc))
    record['rollback_disk_verified'] = complete
    if complete and rows and client is not None:
        try:
            require(matrix.bind_listener(record['proxy_identity']) == record['listener_identity'], 'ROLLBACK_LISTENER')
            for row in rows:
                original, _ = live_read(matrix, engine, row, client.cookie)
                require(sha(original) == row['expected_before'], 'ROLLBACK_HTTP')
            record['rollback_http_verified'] = True
        except BaseException as exc:
            record['rollback_http_verified'] = False
            record['rollback_http_reason'] = safe(exc)
    return complete


def stage(engine, stack, rows, request, source, proof):
    base_fd = engine.directory(BACKUP)
    stack.callback(os.close, base_fd)
    name = 'owner_wow_r62_menu_' + request
    os.mkdir(name, 0o700, dir_fd=base_fd)
    os.fsync(base_fd)
    root = BACKUP / name
    root_fd = engine.directory(root)
    stack.callback(os.close, root_fd)
    core = os.fstat(root_fd)
    require(stat.S_IMODE(core.st_mode) == 0o700, 'BACKUP_DIRECTORY_MODE')
    entries = []
    for index, row in enumerate(rows):
        require(os.fstat(row['site_fd']).st_dev == core.st_dev, 'EXCHANGE_FILESYSTEM')
        folder = str(index)
        os.mkdir(folder, 0o700, dir_fd=root_fd)
        os.fsync(root_fd)
        row['backup_path'] = root / folder
        row['backup_fd'] = engine.directory(row['backup_path'])
        stack.callback(os.close, row['backup_fd'])
        before = engine.create(row['backup_fd'], 'before.bin', row['raw_before'])
        candidate = engine.create(row['backup_fd'], 'exchange.js', row['raw_after'], row['meta_before']['mode'])
        require(candidate['uid'] == row['meta_before']['uid'] and candidate['gid'] == row['meta_before']['gid'],
                'FILE_OWNERSHIP')
        row['pair'] = {'before': row['meta_before'], 'candidate': candidate}
        entries.append({'relative': row['relative'], 'folder': folder, 'before': row['expected_before'],
                        'after': row['expected_after'], 'before_copy': before, 'pair': row['pair']})
    engine.private_json(root_fd, 'prepared.json', {
        'schema': 'NOX_WOW_R6_2_MENU_PREPARED_V1', 'request': request, 'source_sha': source,
        'archive_sha256': ZIP_SHA, 'changes': entries, 'preserved': proof,
    })
    return root_fd, str(root.relative_to(ROOT))


def run(record):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source)
            and os.geteuid() == 0, 'OWNER_CONTEXT')
    record.update(request=request, source_sha=source)
    matrix, engine, auth = modules()
    files = payload(engine)
    rows, changed, attempted, clients = [], [], [], []
    client = None
    journal = None
    failure = None

    class ScopedClient(auth.OwnerClient):
        def __init__(self, cookie=None):
            require(not clients, 'AUTH_COUNT')
            super().__init__(cookie)
            clients.append(self)

    with ExitStack() as stack:
        matrix.gate()
        maintenance_fd = stack.enter_context(engine.lease(matrix.LEASE, shared=True))
        write_fd = None
        process = matrix.proxy_identity()
        listeners = matrix.bind_listener(process)
        record.update(proxy_identity=process, listener_identity=listeners)
        require(matrix.served(matrix.REQUIRED[0])[0] == 401, 'OWNER_AUTH_GATE')
        try:
            client = ScopedClient.authenticate()
            require(matrix.bind_listener(process) == listeners, 'PROXY_LIFETIME')
            proof = protected(matrix, auth, client.cookie)
            for relative, (spec, after) in files.items():
                full = matrix.SITE / relative
                site_fd = engine.directory(full.parent)
                stack.callback(os.close, site_fd)
                outcome = {'path': relative}
                record['files'].append(outcome)
                row = {'relative': relative, 'directory': full.parent, 'basename': full.name,
                       'site_fd': site_fd, 'raw_after': after, 'receipt': outcome,
                       'expected_after': spec['after_sha256']}
                before, info = live_read(matrix, engine, row, client.cookie)
                old = sha(before)
                outcome.update(before=projected(before, info), expected_after=row['expected_after'])
                require(old in (spec['conditional_before_sha256'], row['expected_after']), 'UNKNOWN_NATIVE_PREIMAGE')
                row.update(raw_before=before, meta_before=info, expected_before=old)
                rows.append(row)
                if old == row['expected_after']:
                    outcome['state'] = 'ALREADY_ACTIVE'
                else:
                    changed.append(row)
            if changed:
                write_fd = stack.enter_context(engine.lease(WRITE_LOCK, create_file=True))
                journal, record['private_backup'] = stage(engine, stack, changed, request, source, proof)
            for row in changed:
                matrix.gate()
                verify_lease(maintenance_fd, matrix.LEASE)
                verify_lease(write_fd, WRITE_LOCK)
                require(matrix.bind_listener(process) == listeners, 'PROXY_LIFETIME')
                original, info = live_read(matrix, engine, row, client.cookie)
                require(original == row['raw_before'] and info == row['meta_before'], 'CAS_PREIMAGE')
                engine.named_directory(row['backup_path'], row['backup_fd'])
                switch_names(engine, row)
                attempted.append(row)
                engine.publish(row['site_fd'], row['backup_fd'], row['pair'], {})
                installed, after = live_read(matrix, engine, row, client.cookie)
                require(installed == row['raw_after'] and engine.moved_equal(after, row['pair']['candidate']),
                        'CAS_POSTIMAGE')
                row['receipt'].update(state='STATIC_DISK_HTTP_VERIFIED', after=projected(installed, after))
            for row in rows:
                final, _ = live_read(matrix, engine, row, client.cookie)
                require(sha(final) == row['expected_after'], 'FINAL_POSTIMAGE')
            require(protected(matrix, auth, client.cookie) == proof, 'NATIVE_CHAT_CHANGED')
            matrix.gate()
            verify_lease(maintenance_fd, matrix.LEASE)
            if write_fd is not None:
                verify_lease(write_fd, WRITE_LOCK)
        except BaseException as exc:
            failure = exc
            rollback(matrix, engine, attempted, record, client)
        finally:
            if clients:
                try:
                    require(matrix.bind_listener(process) == listeners, 'PROXY_LIFETIME')
                    clients[0].close()
                    record['owner_session_closed'] = True
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                        rollback(matrix, engine, attempted, record, None)
        if failure is not None:
            record['reason'] = safe(failure)
            if journal is not None:
                engine.private_json(journal, 'hold.json', record)
            raise failure
        try:
            matrix.gate()
            verify_lease(maintenance_fd, matrix.LEASE)
            if write_fd is not None:
                verify_lease(write_fd, WRITE_LOCK)
            record.update(state='MENU_STATIC_DISK_HTTP_VERIFIED', changed_files=len(changed),
                          native_chat_preserved=proof)
            if journal is not None:
                sealed = engine.private_json(journal, 'receipt.json', record)
                record['private_receipt_sha256'] = sealed['sha256']
        except BaseException:
            rollback(matrix, engine, attempted, record, None)
            raise


if __name__ == '__main__':
    result = {'schema': 'NOX_WOW_R6_2_MENU_ONLY_RECEIPT_V1', 'state': 'HOLD',
              'archive_sha256': ZIP_SHA, 'files': [], 'started_at': int(time.time()),
              'service_restarts': 0, 'application_posts': 0, 'asset_bytes_exported': False,
              'browser_acceptance_verified': False}
    signal.signal(signal.SIGALRM, check_stop)
    signal.signal(signal.SIGTERM, check_stop)
    signal.alarm(150)
    try:
        run(result)
        exit_code = 0
    except BaseException as error:
        result.update(state='HOLD', reason=result.get('reason', safe(error)))
        exit_code = 2
    finally:
        signal.alarm(0)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'wow_r62_menu_only', 'data': result},
          separators=(',', ':'), sort_keys=True), flush=True)
    if exit_code == 0:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    raise SystemExit(exit_code)
