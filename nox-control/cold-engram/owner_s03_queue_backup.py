"""Create one private, authenticated NOX S03 and dispatcher backup on host disk."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time


ROOT = Path('/root/nox')
DATABASE = Path('kb/knowledge.sqlite')
QUEUE = Path('state/dispatcher/state.json')
JOURNAL = Path('state/dispatcher/queue.jsonl')
MIB = 1024**2
MAX_DB = 512 * MIB
MAX_QUEUE = 8 * MIB
MAX_JOURNAL = 64 * MIB
MAX_LINE = 256 * 1024
RESERVE = 128 * MIB
DEADLINE_SECONDS = 60
SIGNATURE = re.compile(r'(?:[0-9a-f]{64}|[0-9a-f]{128})').fullmatch
SHA = re.compile(r'[0-9a-f]{64}').fullmatch
REQUEST = re.compile(r'[1-9][0-9]{0,19}').fullmatch


class BackupHold(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupRequest:
    request_id: str
    database_device: int
    database_inode: int
    queue_sha256: str
    journal_sha256: str


def require(condition, code):
    if not condition:
        raise BackupHold('HOLD_S03_QUEUE_BACKUP_' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def inode(info):
    return info.st_dev, info.st_ino


def metadata(info):
    return (*inode(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_mode, info.st_nlink)


def trusted_path(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    for directory in path.parents:
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode), 'PATH_SCOPE')
    return path


def trusted_file(info, limit):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022
            and 0 <= info.st_size <= limit, 'FILE_SCOPE')


@contextmanager
def opened(path, limit):
    path = trusted_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        original = os.fstat(stream.fileno())
        trusted_file(original, limit)
        require(inode(path.lstat()) == inode(original), 'FILE_REPLACED')
        yield stream, original


def verified_sqlite_source(path, request):
    with opened(path, MAX_DB) as (stream, info):
        header = stream.read(100)
        require(inode(info) == (request.database_device, request.database_inode)
                and header.startswith(b'SQLite format 3\0')
                and header[18:20] in (b'\x01\x01', b'\x02\x02'), 'DATABASE_PIN')
    present = set()
    for suffix in ('-wal', '-shm', '-journal'):
        try:
            sidecar = Path(str(path) + suffix).lstat()
        except FileNotFoundError:
            continue
        trusted_file(sidecar, MAX_DB)
        require(sidecar.st_dev == request.database_device, 'DATABASE_SIDECAR_DEVICE')
        present.add(suffix)
    if header[18:20] == b'\x02\x02':
        require({'-wal', '-shm'} <= present, 'EXISTING_WAL_SIDECARS')


def sqlite_schema(connection):
    names = {name for name, in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('s03_items','s03_fts')")}
    require(names == {'s03_items', 's03_fts'}, 'DATABASE_SCHEMA')


def sqlite_backup(source, target, request, check):
    verified_sqlite_source(source, request)
    target.touch(mode=0o600, exist_ok=False)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=.2)) as database, \
            closing(sqlite3.connect(target, timeout=.2)) as copy:
        database.execute('PRAGMA query_only=ON')
        database.execute('PRAGMA cache_size=-2048')
        sqlite_schema(database)
        page_size, = database.execute('PRAGMA page_size').fetchone()
        pages, = database.execute('PRAGMA page_count').fetchone()
        require(512 <= page_size <= 65536 and 0 < pages * page_size <= MAX_DB, 'DATABASE_SIZE')
        copy.execute('PRAGMA cache_size=-2048')
        copy.execute(f'PRAGMA page_size={page_size}')
        copy.execute(f'PRAGMA max_page_count={MAX_DB // page_size}')

        def progress(_status, _remaining, total):
            check()
            require(total * page_size <= MAX_DB, 'DATABASE_SIZE')

        database.backup(copy, pages=256, progress=progress, sleep=.02)
        require(copy.execute('PRAGMA journal_mode=DELETE').fetchone() == ('delete',), 'BACKUP_JOURNAL')
    verified_sqlite_source(source, request)
    for suffix in ('-wal', '-shm', '-journal'):
        require(not os.path.lexists(str(target) + suffix), 'BACKUP_SIDECAR')
    with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=.2)) as reopened:
        reopened.execute('PRAGMA cache_size=-2048')

        def check_query():
            check()
            return 0

        reopened.set_progress_handler(check_query, 10000)
        sqlite_schema(reopened)
        require(reopened.execute('PRAGMA quick_check(1)').fetchone() == ('ok',), 'BACKUP_INTEGRITY')


def decode_document(raw):
    def unique(entries):
        result = dict(entries)
        require(len(result) == len(entries), 'DUPLICATE_QUEUE_FIELD')
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict), 'QUEUE_SCHEMA')
    return value


def copy_pinned(source, target, expected, limit, check, *, journal=False):
    digest = hashlib.sha256()
    total = 0
    checked = -512 * 1024
    with opened(source, limit) as (incoming, info):
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'wb') as outgoing:
            while True:
                if total - checked >= 512 * 1024:
                    check()
                    checked = total
                data = incoming.readline(MAX_LINE + 1) if journal else incoming.read(512 * 1024)
                if not data:
                    break
                total += len(data)
                require(total <= limit, 'QUEUE_SIZE')
                if journal:
                    require(len(data) <= MAX_LINE and data.endswith(b'\n'), 'JOURNAL_PARTIAL_LINE')
                    decode_document(data)
                digest.update(data)
                outgoing.write(data)
            require(total == info.st_size and digest.hexdigest() == expected
                    and metadata(os.fstat(incoming.fileno())) == metadata(info)
                    and metadata(source.lstat()) == metadata(info), 'QUEUE_OR_JOURNAL_PIN')
            outgoing.flush()
            os.fsync(outgoing.fileno())
    if not journal:
        with opened(target, limit) as (copy, _):
            tasks = decode_document(copy.read(limit + 1)).get('tasks')
        require(isinstance(tasks, dict) and all(isinstance(row, dict) and isinstance(row.get('status'), str)
                                                for row in tasks.values()), 'QUEUE_SCHEMA')
    return metadata(info)


def hash_file(path, limit, check):
    digest = hashlib.sha256()
    with opened(path, limit) as (stream, info):
        for data in iter(lambda: stream.read(512 * 1024), b''):
            check()
            digest.update(data)
        os.fsync(stream.fileno())
        require(metadata(os.fstat(stream.fileno())) == metadata(info)
                == metadata(path.lstat()), 'BACKUP_FILE_CHANGED')
    return {'sha256': digest.hexdigest(), 'bytes': info.st_size}


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def backup(request, destination, *, native_lease, assert_durable, sign_digest, verify_signature):
    """Local-only. Callbacks come from the authenticated owner application.

    native_lease() yields checkpoint() -> True while authorized. assert_durable
    takes (directory_fd, required_bytes) and attests persistent host storage and
    quota. The signer and verifier accept only the canonical manifest digest.
    """
    require(isinstance(request, BackupRequest) and isinstance(request.request_id, str)
            and REQUEST(request.request_id) and type(request.database_device) is int
            and type(request.database_inode) is int and request.database_inode > 0
            and all(isinstance(pin, str) and SHA(pin)
                    for pin in (request.queue_sha256, request.journal_sha256)), 'REQUEST')
    with native_lease() as checkpoint:
        require(checkpoint() is True, 'LEASE_OR_DEADLINE')
        return _backup(request, destination, checkpoint, assert_durable, sign_digest, verify_signature)


def _backup(request, destination, checkpoint, assert_durable, sign_digest, verify_signature):
    root = trusted_path(destination)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        owner = os.fstat(directory)
        require(owner.st_uid == os.geteuid() and stat.S_IMODE(owner.st_mode) == 0o700
                and inode(owner) == inode(root.lstat()), 'PRIVATE_DESTINATION')
        upper_bound = MAX_DB + MAX_QUEUE + MAX_JOURNAL + RESERVE
        usage = os.fstatvfs(directory)
        require(usage.f_bavail * usage.f_frsize >= upper_bound
                and assert_durable(directory, upper_bound) is True, 'DURABLE_CAPACITY')
        final = root / ('backup-' + request.request_id)
        require(not os.path.lexists(final), 'BACKUP_EXISTS')
        with tempfile.TemporaryDirectory(prefix='.backup-', dir=root) as staging:
            deadline = time.monotonic() + DEADLINE_SECONDS

            def check():
                require(time.monotonic() < deadline and checkpoint() is True, 'LEASE_OR_DEADLINE')

            check()
            stage = Path(staging)
            db, queue, journal = (ROOT / path for path in (DATABASE, QUEUE, JOURNAL))
            state_before = copy_pinned(queue, stage/'queue.json', request.queue_sha256, MAX_QUEUE, check)
            journal_before = copy_pinned(journal, stage/'queue.jsonl', request.journal_sha256,
                                         MAX_JOURNAL, check, journal=True)
            sqlite_backup(db, stage/'s03.sqlite', request, check)
            files = {name: hash_file(stage/name, limit, check) for name, limit in (
                ('s03.sqlite', MAX_DB), ('queue.json', MAX_QUEUE), ('queue.jsonl', MAX_JOURNAL))}
            require(files['queue.json']['sha256'] == request.queue_sha256
                    and files['queue.jsonl']['sha256'] == request.journal_sha256, 'BACKUP_READBACK')
            manifest = {'schema': 'NOX_S03_QUEUE_BACKUP_V1', 'request_id': request.request_id,
                        'files': files, 'sqlite_online_snapshot': True,
                        'cross_store_transaction': False}
            digest = hashlib.sha256(canonical(manifest)).hexdigest()
            signature = sign_digest(digest)
            require(isinstance(signature, str) and SIGNATURE(signature)
                    and verify_signature(digest, signature) is True, 'SIGNATURE')
            record = canonical({'manifest': manifest, 'manifest_sha256': digest, 'signature': signature})
            fd = os.open(stage/'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(record)
                output.flush()
                os.fsync(output.fileno())
            require((stage/'manifest.json').read_bytes() == record, 'MANIFEST_READBACK')
            fsync_dir(stage)
            check()
            usage = os.fstatvfs(directory)
            require(metadata(queue.lstat()) == state_before and metadata(journal.lstat()) == journal_before
                    and inode(root.lstat()) == inode(owner)
                    and usage.f_bavail * usage.f_frsize >= RESERVE
                    and assert_durable(directory, RESERVE) is True
                    and not os.path.lexists(final), 'FINAL_BINDING')
            os.rename(stage, final)
            os.fsync(directory)
        return {'state': 'BACKUP_DURABLE', 'manifest_sha256': digest, 'signature': signature,
                'files': files}
    finally:
        os.close(directory)
