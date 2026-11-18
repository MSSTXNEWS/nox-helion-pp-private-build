#!/usr/bin/env python3
"""Install pinned, isolated source tools through the existing owner-native route.

This writes only the acceleration tool tree. It never edits a runtime module,
project source, tests, native config, training environment or model checkpoint.
The dedicated tool lock is independent of the native worker maintenance lease.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import base64
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import selectors
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import time
import types

ROOT = Path('/root/nox')
TOOLS = ROOT / 'tools/acceleration'
RELEASE = TOOLS / 'releases/20261118-v1'
CURRENT = TOOLS / 'current.json'
SHIM = TOOLS / 'bin/nox-fast'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
SHA = re.compile(r'[a-f0-9]{64}')
MIB = 1024 * 1024
VERSIONS = {'uv': '0.13.9', 'uvx': '0.13.9', 'ruff': '0.17.5', 'rg': '15.2.0'}
ARCHIVES = {
    'uv': ('0.13.9', 18735070, '58ccf5f1792b8a5a88d01bc910ea131a8b3db4a319a17ad5fad75e0845a3e271',
           'https://github.com/astral-sh/uv/releases/download/0.13.9/uv-x86_64-unknown-linux-musl.tar.gz',
           'uv-x86_64-unknown-linux-musl', ('uv', 'uvx')),
    'ruff': ('0.17.5', 10400704, 'dc94b7e225b8910fb6f55298ada32d00e356dbd195a5ffb647847f388cb54f84',
             'https://github.com/astral-sh/ruff/releases/download/0.17.5/ruff-x86_64-unknown-linux-musl.tar.gz',
             'ruff-x86_64-unknown-linux-musl', ('ruff',)),
    'rg': ('15.2.0', 2265718, '33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c',
           'https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz',
           'ripgrep-15.2.0-x86_64-unknown-linux-musl', ('rg',)),
}
SPEC = {}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


SAFE_HOLD_CODES = frozenset('''
AFTER_TOOL_PROOFS_GUARD ARCHIVE_COMPLETE ARCHIVE_MEMBER ARCHIVE_PATH ARCHIVE_PAYLOAD
ARCHIVE_PAYLOAD_GREW ARCHIVE_SHORT_PAYLOAD ASSET_BOUND ASSET_PIN ASSET_ROLES ASSET_SET
BEFORE_DOWNLOAD_GUARD BEFORE_RELEASE_GUARD BINARY_MEMBER_SCOPE BINARY_VERSION
CHILD_DEADLINE CHILD_OUTPUT_BOUND CLI_PIN CONTROL_CAS_CHANGED CONTROL_PREIMAGE_CHANGED
CREATE_SCOPE DIRECTORY_OWNER DIRECTORY_SCOPE DOWNLOAD_DEADLINE DOWNLOAD_FAILED
DOWNLOAD_READBACK DUPLICATE_JSON_KEY DYNAMIC_INTERPRETER_NOT_ALLOWED ELF_ARCHITECTURE
ELF_HEADERS EXPECTED_BINARY_REGULAR EXTRACTION_TOTAL FILE_BOUND FILE_CHANGED FILE_GREW
FINAL_PUBLICATION_GUARD FOREIGN_CONTROL_FILE FOREIGN_CURRENT_PRESERVED
FOREIGN_RELEASE_FILE HELPER_PIN INSTALLED_TOOL_SET INSTALL_LOCK NATIVE_OWNER_SCOPE
NONFINITE_JSON OWNER_CONTEXT PERMANENT_ENTRYPOINT_PROOF PLATFORM PROJECT_SOURCE_SCOPE
PUBLISHED_READBACK PYTHON_PATH READ_ONLY_TOOL_PROOF REGULAR_FILE RELEASE_FILESET
RELEASE_FILE_COUNT RELEASE_PREIMAGE RENAME_NOREPLACE_UNAVAILABLE SHIM_PIN SHORT_WRITE
SPEC_SCHEMA STAGED_BINARY_PIN STAGING_IDENTITY TOOL_BINARY_PROOF TOOL_PROFILE TOOL_SET
UPSTREAM_PIN
'''.split())
SAFE_HELPER_HOLDS = frozenset('''
PATH_SCOPE FILE_BOUND FILE_CHANGED UPDATE_DIRECTOR_CHANGED UPDATE_WORKER_COUNT
UPDATE_WORKER_CHANGED PROTECTED_PROCESS_chat PROTECTED_PROCESS_proxy PROTECTED_PROCESS_web
'''.split())
SAFE_EXCEPTION_CLASSES = frozenset('''
Hold OSError FileNotFoundError PermissionError NotADirectoryError IsADirectoryError
BlockingIOError TimeoutError FileExistsError UnicodeDecodeError JSONDecodeError
ValueError KeyError TypeError AttributeError IndexError SyntaxError OverflowError
MemoryError RuntimeError ImportError ModuleNotFoundError NameError AssertionError
SystemExit KeyboardInterrupt SubprocessError TimeoutExpired
'''.split())


def safe_failure(exc):
    """Project fixed identifiers only; exception messages may contain host data."""
    name = type(exc).__name__
    result = {'state':'HOLD_ACCELERATION_UNCLASSIFIED',
              'exception_class':name if name in SAFE_EXCEPTION_CLASSES else 'OTHER'}
    code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
    if code in {'HOLD_ACCELERATION_' + item for item in SAFE_HOLD_CODES}:
        result['state'] = code
    elif code in {'HOLD_COMPLETE_EXECUTOR_' + item for item in SAFE_HELPER_HOLDS}:
        result['state'] = code
    if isinstance(exc,OSError) and type(exc.errno) is int and exc.errno in errno.errorcode:
        result['errno'] = exc.errno
    return result


def require(value, code):
    if not value:
        raise Hold('HOLD_ACCELERATION_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    encoded(value)
    return value


def identity(info):
    return (info.st_dev, info.st_ino, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_uid)


def directory(path, create=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'DIRECTORY_SCOPE')
    if create:
        require(path == ROOT / 'tools' or path.is_relative_to(TOOLS), 'CREATE_SCOPE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    current = Path('/')
    try:
        for part in path.parts[1:]:
            current /= part
            if create and (current == ROOT / 'tools' or current.is_relative_to(TOOLS)):
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            if current == ROOT / 'tools' or current.is_relative_to(TOOLS):
                info = os.fstat(fd)
                require(info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'DIRECTORY_OWNER')
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_regular(path, limit):
    parent = directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and not info.st_mode & 0o022
                and 0 <= info.st_size <= limit, 'REGULAR_FILE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def consume(fd, limit, materialize=False):
    before = os.fstat(fd)
    require(0 <= before.st_size <= limit, 'FILE_BOUND')
    hasher, chunks, count = hashlib.sha256(), [], 0
    while True:
        block = os.read(fd, min(65536, before.st_size - count + 1))
        if not block:
            break
        count += len(block)
        require(count <= before.st_size, 'FILE_GREW')
        hasher.update(block)
        if materialize:
            chunks.append(block)
    require(count == before.st_size and identity(before) == identity(os.fstat(fd)), 'FILE_CHANGED')
    return hasher.hexdigest(), count, b''.join(chunks) if materialize else None


def read(path, limit=65536):
    fd = open_regular(path, limit)
    try:
        return consume(fd, limit, True)[2]
    finally:
        os.close(fd)


def optional(path, limit=65536):
    try:
        return read(path, limit)
    except FileNotFoundError:
        return None


def write_all(fd, raw):
    remaining = memoryview(raw)
    while remaining:
        count = os.write(fd, remaining)
        require(count > 0, 'SHORT_WRITE')
        remaining = remaining[count:]


def new_file(path, raw, mode=0o600):
    parent = directory(Path(path).parent, True)
    try:
        fd = os.open(Path(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     mode, dir_fd=parent)
        try:
            write_all(fd, raw)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def publish_equal_or_new(path, raw, mode=0o600):
    """Atomic create-no-clobber; an existing different owner's bytes never move."""
    current = optional(path)
    if current is not None:
        require(current == raw, 'FOREIGN_CONTROL_FILE')
        return False
    parent = directory(Path(path).parent, True)
    temporary = '.publish-' + os.urandom(16).hex()
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     mode, dir_fd=parent)
        write_all(fd, raw)
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.close(fd)
        fd = None
        try:
            os.link(temporary, Path(path).name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            created = True
        except FileExistsError:
            require(read(path) == raw, 'CONTROL_CAS_CHANGED')
            created = False
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        return created
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def clean_env():
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
            'UV_PYTHON_DOWNLOADS': 'never', 'UV_OFFLINE': 'true', 'UV_NO_CONFIG': 'true',
            'RAYON_NUM_THREADS': '1', 'NO_COLOR': '1'}


def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_AS, (512 * MIB, 512 * MIB))


def run_bounded(argv, *, pass_fds=(), seconds=10, output_limit=65536):
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, env=clean_env(), cwd='/', close_fds=True,
        pass_fds=pass_fds, preexec_fn=child_limits, start_new_session=True)
    selector, output = selectors.DefaultSelector(), bytearray()
    deadline = time.monotonic() + seconds
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'CHILD_DEADLINE')
            for key, _ in selector.select(min(.1, remaining)):
                block = os.read(key.fileobj.fileno(), min(65536, output_limit - len(output) + 1))
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(block)
                require(len(output) <= output_limit, 'CHILD_OUTPUT_BOUND')
        code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        return code, bytes(output)
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


DOWNLOAD_CODE = r'''
import hashlib, os, sys, urllib.request, urllib.parse
allowed = {'github.com', 'release-assets.githubusercontent.com', 'releases.astral.sh'}
def valid(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in allowed or p.port not in (None,443) or p.username or p.password or p.fragment:
        raise ValueError('DOWNLOAD_ORIGIN')
class Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        valid(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
try:
    url, expected, pin, outfd = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
    valid(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())
    request = urllib.request.Request(url, headers={'User-Agent':'NOX-pinned-tools/1','Accept':'application/octet-stream'})
    total, hasher = 0, hashlib.sha256()
    with opener.open(request, timeout=20) as response:
        valid(response.geturl())
        if response.status != 200:
            raise ValueError('DOWNLOAD_STATUS')
        declared = response.headers.get('Content-Length')
        if declared is not None and int(declared) != expected:
            raise ValueError('DOWNLOAD_LENGTH')
        while True:
            block = response.read1(min(65536, expected-total+1))
            if not block:
                break
            total += len(block)
            if total > expected:
                raise ValueError('DOWNLOAD_BOUND')
            hasher.update(block)
            view = memoryview(block)
            while view:
                count = os.write(outfd,view)
                if count <= 0:
                    raise ValueError('SHORT_WRITE')
                view = view[count:]
    if total != expected or hasher.hexdigest() != pin:
        raise ValueError('DOWNLOAD_SHA')
    os.fsync(outfd)
except BaseException:
    sys.exit(2)
'''


def download(row, path, deadline):
    parent = directory(path.parent)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'DOWNLOAD_DEADLINE')
        code, output = run_bounded([sys.executable, '-I', '-B', '-c', DOWNLOAD_CODE,
            row['url'], str(row['size_bytes']), row['sha256'], str(fd)],
            pass_fds=(fd,), seconds=remaining, output_limit=4096)
        require(code == 0 and not output and time.monotonic() <= deadline, 'DOWNLOAD_FAILED')
        os.lseek(fd, 0, os.SEEK_SET)
        pin, size, _ = consume(fd, 32 * MIB)
        require(pin == row['sha256'] and size == row['size_bytes'], 'DOWNLOAD_READBACK')
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    finally:
        os.close(parent)


def elf_static(fd, size):
    header = os.pread(fd, 64, 0)
    require(len(header) == 64 and header[:7] == b'\x7fELF\x02\x01\x01'
            and struct.unpack_from('<H', header, 18)[0] == 62, 'ELF_ARCHITECTURE')
    offset = struct.unpack_from('<Q', header, 32)[0]
    width, count = struct.unpack_from('<HH', header, 54)
    require(width == 56 and 1 <= count <= 256 and offset + width * count <= size, 'ELF_HEADERS')
    table = os.pread(fd, width * count, offset)
    require(len(table) == width * count and all(struct.unpack_from('<I', table, n * width)[0] != 3
            for n in range(count)), 'DYNAMIC_INTERPRETER_NOT_ALLOWED')


def extract(row, archive_fd, stage_release, byte_total):
    expected = {item['archive_path']: item for item in row['members']}
    found, entries = {}, set()
    archive_before = identity(os.fstat(archive_fd))
    with os.fdopen(os.dup(archive_fd), 'rb', buffering=0) as stream:
        with tarfile.open(fileobj=stream, mode='r:gz') as archive:
            for member in archive:
                name = member.name.rstrip('/')
                posix = PurePosixPath(name)
                require(name and not posix.is_absolute() and '..' not in posix.parts
                        and '\\' not in name and '\x00' not in name
                        and name == posix.as_posix() and name not in entries, 'ARCHIVE_PATH')
                entries.add(name)
                require(len(entries) <= 512 and (member.isdir() or member.isreg())
                        and member.sparse is None and 0 <= member.size <= 256 * MIB,
                        'ARCHIVE_MEMBER')
                byte_total[0] += member.size
                require(byte_total[0] <= 512 * MIB, 'EXTRACTION_TOTAL')
                if name not in expected:
                    continue
                require(member.isreg(), 'EXPECTED_BINARY_REGULAR')
                target = stage_release / expected[name]['relative_install_path']
                parent = directory(target.parent, True)
                fd = None
                try:
                    fd = os.open(target.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o755, dir_fd=parent)
                    source = archive.extractfile(member)
                    require(source is not None, 'ARCHIVE_PAYLOAD')
                    count, hasher = 0, hashlib.sha256()
                    with source:
                        while count < member.size:
                            block = source.read(min(65536, member.size - count))
                            require(bool(block), 'ARCHIVE_SHORT_PAYLOAD')
                            count += len(block)
                            hasher.update(block)
                            write_all(fd, block)
                        require(not source.read(1), 'ARCHIVE_PAYLOAD_GREW')
                    os.fchmod(fd, 0o755)
                    os.fsync(fd)
                    elf_static(fd, count)
                    binary = expected[name]['binary']
                    found[binary] = {'path': expected[name]['installed_path'], 'sha256': hasher.hexdigest(),
                                     'version': row['version']}
                    os.fsync(parent)
                finally:
                    if fd is not None:
                        os.close(fd)
                    os.close(parent)
    require(set(found) == {item['binary'] for item in row['members']}
            and identity(os.fstat(archive_fd)) == archive_before, 'ARCHIVE_COMPLETE')
    return found


def verify_versions(tools, stage_release):
    # All writable extraction FDs are closed before executing a binary. uvx may
    # locate its sibling uv, so the complete archive is materialized first.
    versions = {}
    for name, entry in tools.items():
        path = stage_release / Path(entry['path']).relative_to(RELEASE)
        fd = open_regular(path, 256 * MIB)
        try:
            require(consume(fd,256*MIB)[0] == entry['sha256'], 'STAGED_BINARY_PIN')
            code, output = run_bounded(['/proc/self/fd/' + str(fd), '--version'],
                                       pass_fds=(fd,),seconds=5,output_limit=4096)
            label = {'rg':'ripgrep','uvx':'(?:uvx|uv)'}.get(name,name)
            line = output.decode('utf-8','strict').splitlines()[0] if output else ''
            require(code == 0 and re.match(r'^'+label+r'\s+'+re.escape(entry['version'])+r'(?:\s|$)',line),
                    'BINARY_VERSION')
            versions[name] = {'version':entry['version'],'output_sha256':digest(output)}
        finally:
            os.close(fd)
    return versions


def move_release_no_replace(source):
    parent = directory(RELEASE.parent, True)
    original_parent = directory(source.parent)
    try:
        library = ctypes.CDLL(None, use_errno=True)
        function = getattr(library, 'renameat2', None)
        require(function is not None, 'RENAME_NOREPLACE_UNAVAILABLE')
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        outcome = function(original_parent, os.fsencode(source.name), parent, os.fsencode(RELEASE.name), 1)
        if outcome != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                return False
            raise OSError(error, 'RELEASE_RENAME_FAILED')
        os.fsync(parent)
        os.fsync(original_parent)
        return True
    finally:
        os.close(original_parent)
        os.close(parent)


SHIM_TEMPLATE = r'''#!@PYTHON@ -I
import hashlib, json, os, stat, sys
sys.dont_write_bytecode = True
from pathlib import Path
def fail():
    raise SystemExit('HOLD_NOX_FAST_SHIM_PIN')
def opened(path, limit):
    p=Path(path); directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    finally:
        os.close(directory)
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid() or info.st_mode&0o022 or not 0<=info.st_size<=limit:
        os.close(fd);fail()
    raw=b''
    while True:
        block=os.read(fd,min(65536,info.st_size-len(raw)+1))
        if not block:break
        raw+=block
        if len(raw)>info.st_size:os.close(fd);fail()
    after=os.fstat(fd)
    keys=('st_dev','st_ino','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    if len(raw)!=info.st_size or any(getattr(info,k)!=getattr(after,k) for k in keys):
        os.close(fd);fail()
    return fd,raw
def checked(path,pin,limit,keep=False):
    fd,raw=opened(path,limit)
    if hashlib.sha256(raw).hexdigest()!=pin:os.close(fd);fail()
    if keep:return fd
    os.close(fd)
for arg in sys.argv[1:]:
    if arg in ('--manifest','--manifest-sha256') or arg.startswith(('--manifest=','--manifest-sha256=')):fail()
checked(@CURRENT@,@POINTER_PIN@,65536)
checked(@MANIFEST@,@MANIFEST_PIN@,65536)
fd=checked(@CLI@,@CLI_PIN@,524288,True)
os.set_inheritable(fd,True)
os.execv(@PYTHON_REPR@,[@PYTHON_REPR@,'-I','-B','/proc/self/fd/'+str(fd),
    '--manifest',@MANIFEST@,'--manifest-sha256',@MANIFEST_PIN@,*sys.argv[1:]])
'''


def shim_bytes(manifest_pin, pointer_pin, cli_pin):
    python = str(Path(sys.executable).resolve())
    require(re.fullmatch(r'/[A-Za-z0-9_./-]{1,220}', python) is not None, 'PYTHON_PATH')
    replacements = {'@PYTHON@':python,'@PYTHON_REPR@':repr(python),
        '@CURRENT@':repr(str(CURRENT)), '@POINTER_PIN@':repr(pointer_pin),
        '@MANIFEST@':repr(str(RELEASE / 'manifest.json')), '@MANIFEST_PIN@':repr(manifest_pin),
        '@CLI@':repr(str(RELEASE / 'owner_nox_fast_tools.py')), '@CLI_PIN@':repr(cli_pin)}
    text = SHIM_TEMPLATE
    for old, new in replacements.items():
        text = text.replace(old, new)
    compile(text, '<nox-fast-shim>', 'exec')
    return text.encode()


def verify_release(files):
    expected = set(files)
    seen = set()
    directories = 0
    fd = directory(RELEASE)
    os.close(fd)
    for parent, dirs, names in os.walk(RELEASE, followlinks=False):
        directories += 1
        require(directories <= 32 and len(dirs) <= 16 and len(names) <= 16
                and len(seen) <= 32, 'RELEASE_FILE_COUNT')
        for name in dirs:
            fd = directory(Path(parent) / name)
            os.close(fd)
        for name in names:
            path = Path(parent) / name
            relative = path.relative_to(RELEASE).as_posix()
            require(relative in expected, 'FOREIGN_RELEASE_FILE')
            fd = open_regular(path, 256 * MIB)
            try:
                require(consume(fd, 256 * MIB)[0] == files[relative], 'RELEASE_PREIMAGE')
            finally:
                os.close(fd)
            seen.add(relative)
    require(seen == expected, 'RELEASE_FILESET')


def run(bundle, spec, diagnostic=None):
    diagnostic = {} if diagnostic is None else diagnostic
    def phase(name):
        diagnostic.update(phase=name,operation='NONE')
    started = time.monotonic()
    phase('OWNER_CONTEXT')
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID',''), os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[a-f0-9]{40}',source), 'OWNER_CONTEXT')
    phase('PLATFORM')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'PLATFORM')
    phase('SPEC_SCHEMA')
    require(spec.get('schema') == 'NOX_ACCELERATION_INSTALL_SPEC_V1', 'SPEC_SCHEMA')
    phase('ASSET_SET')
    pins = spec.get('assets')
    require(isinstance(pins,dict) and set(pins) == set(bundle) and len(pins) == 4, 'ASSET_SET')
    phase('ASSET_DECODE_AND_PIN')
    assets = {}
    for name, pin in pins.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',name) and isinstance(pin,str) and SHA.fullmatch(pin)
                and isinstance(bundle[name],str) and len(bundle[name]) <= 1400000, 'ASSET_BOUND')
        raw = base64.b64decode(bundle[name],validate=True)
        require(len(raw) <= MIB and digest(raw) == pin, 'ASSET_PIN')
        assets[name] = raw
    phase('ASSET_ROLES')
    names = [spec[k] for k in ('helper_asset','lock_asset','profile_asset','cli_asset')]
    require(len(set(names)) == 4 and set(names) == set(assets), 'ASSET_ROLES')
    require(digest(assets[spec['helper_asset']]) == HELPER_SHA, 'HELPER_PIN')
    phase('HELPER_LOAD')
    helper = types.ModuleType('_nox_acceleration_helper')
    exec(compile(assets[spec['helper_asset']], '<pinned-helper>', 'exec'),helper.__dict__)
    phase('LOCK_PARSE')
    lock = strict_json(assets[spec['lock_asset']])
    phase('PROFILE_PARSE')
    profile = strict_json(assets[spec['profile_asset']])
    phase('TOOL_PROFILE')
    require(lock.get('schema') == 'NOX_ACCELERATION_TOOLCHAIN_LOCK_V1'
            and lock.get('release_root') == str(RELEASE)
            and profile.get('schema') == 'NOX_ACCELERATION_PROFILE_V1'
            and profile.get('release_root') == str(RELEASE), 'TOOL_PROFILE')
    phase('TOOL_METADATA')
    rows = lock.get('tools')
    require(isinstance(rows,list) and len(rows) == 3 and {r['name'] for r in rows} == set(ARCHIVES), 'TOOL_SET')
    for row in rows:
        version,size,pin,url,prefix,binaries = ARCHIVES[row['name']]
        require((row.get('version'),row.get('size_bytes'),row.get('sha256'),row.get('url')) == (version,size,pin,url),
                'UPSTREAM_PIN')
        expected = [{'archive_path':prefix+'/'+binary,
            'relative_install_path':row['name']+'/'+version+'/'+binary,
            'installed_path':str(RELEASE / row['name'] / version / binary),'binary':binary} for binary in binaries]
        require(row.get('members') == expected, 'BINARY_MEMBER_SCOPE')
    phase('CLI_COMPILE')
    cli_raw = assets[spec['cli_asset']]
    compile(cli_raw, '<pinned-nox-fast>', 'exec')
    observed_config_pins = set()
    def guard():
        diagnostic['operation'] = 'CONFIG_READ'
        raw = helper.read_regular(ROOT / 'config/owner_native_subagents.json',2*MIB)
        diagnostic['operation'] = 'CONFIG_PARSE'
        config = strict_json(raw)
        diagnostic['operation'] = 'NATIVE_OWNER_SCOPE'
        require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
                and config.get('owner_authorized') is True and config.get('instance_id') == 60509551
                and config.get('target') == config.get('global_worker_cap') == 3
                and config.get('execution_mode') == 'NATIVE_PROJECT_V1'
                and helper.stop_clear(ROOT), 'NATIVE_OWNER_SCOPE')
        diagnostic['operation'] = 'PROJECT_SOURCE_SCOPE'
        scope = config.get('project_executor',{}).get('roots',{}).get('NOX_PROJECT_SOURCE',{})
        require(scope.get('path') == str(ROOT/'projects/owner_executor/source_workspace')
                and scope.get('integration_kind') == 'SOURCE_WORKSPACE'
                and isinstance(scope.get('allowed_paths'),list) and 1 <= len(scope['allowed_paths']) <= 256,
                'PROJECT_SOURCE_SCOPE')
        observed_config_pins.add(digest(raw))
        diagnostic['operation'] = 'DIRECTOR_AND_WORKERS'
        processes = helper.expected_processes(spec)
        diagnostic['operation'] = 'PROTECTED_PROCESSES'
        protected = helper.protected_snapshot(spec)
        diagnostic['operation'] = 'NONE'
        return {'project_scope_sha256':digest(encoded(scope)),'processes':processes,'protected':protected}
    phase('BASELINE_GUARD')
    baseline = guard()
    phase('TOOLS_DIRECTORY')
    root_fd = directory(TOOLS,True)
    lock_fd = stage = None
    receipt = {'schema':'NOX_ACCELERATION_INSTALL_RECEIPT_V1','request':request,'source_sha':source,
               'state':'PREFLIGHT','source_writes':0,'runtime_writes':0,'config_writes':0,
               'service_restarts':0,'model_downloads':0,'python_downloads':0,'optimizer_updates':0,
               'original_tasks_accepted':0,'measured_latency_improvement':False}
    try:
        phase('INSTALL_LOCK')
        lock_fd = os.open('install.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,
                          0o600,dir_fd=root_fd)
        info = os.fstat(lock_fd)
        named = os.stat('install.lock',dir_fd=root_fd,follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and not info.st_mode & 0o022 and (info.st_dev,info.st_ino) == (named.st_dev,named.st_ino), 'INSTALL_LOCK')
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        phase('BEFORE_DOWNLOAD_GUARD')
        require(guard() == baseline, 'BEFORE_DOWNLOAD_GUARD')
        phase('CONTROL_PREIMAGES')
        old_pointer,old_shim = optional(CURRENT),optional(SHIM)
        phase('STAGING_CREATE')
        stage = Path(tempfile.mkdtemp(prefix='.install-'+request+'-',dir=TOOLS))
        stage_identity = identity(os.stat(stage,follow_symlinks=False))[:2]
        stage_release = stage / 'release'
        stage_fd = directory(stage_release,True)
        os.close(stage_fd)
        deadline = time.monotonic() + 180
        tools, total = {}, [0]
        for row in rows:
            phase({'uv':'DOWNLOAD_UV','ruff':'DOWNLOAD_RUFF','rg':'DOWNLOAD_RG'}[row['name']])
            fd = download(row,stage/row['archive_name'],deadline)
            try:
                phase({'uv':'EXTRACT_UV','ruff':'EXTRACT_RUFF','rg':'EXTRACT_RG'}[row['name']])
                tools.update(extract(row,fd,stage_release,total))
            finally:
                os.close(fd)
        phase('VERSION_PROOFS')
        require(set(tools) == set(VERSIONS), 'INSTALLED_TOOL_SET')
        version_proofs = verify_versions(tools,stage_release)
        phase('MANIFEST_BUILD')
        manifest = {'schema':'NOX_ACCELERATION_INSTALLED_V1','release_id':'20261118-v1',
            'release_root':str(RELEASE),'tools':tools,
            'cli':{'path':str(RELEASE/'owner_nox_fast_tools.py'),'sha256':digest(cli_raw)},
            'profile':{'path':str(RELEASE/'profile.json'),'sha256':digest(assets[spec['profile_asset']])},
            'upstream_lock':{'path':str(RELEASE/'toolchain.lock.json'),'sha256':digest(assets[spec['lock_asset']])},
            'upstream_archives':{r['name']:{k:r[k] for k in ('version','url','sha256','size_bytes')} for r in rows},
            'platform':'linux-x86_64','linkage':'NO_ELF_PT_INTERP',
            'daemon_count':0,'native_test_acceptance':False,'model_quality_claim':False}
        raw = encoded(manifest)
        pointer = encoded({'schema':'NOX_ACCELERATION_CURRENT_V1','manifest_path':str(RELEASE/'manifest.json'),
                           'manifest_sha256':digest(raw),'release_root':str(RELEASE),
                           'cli_path':manifest['cli']['path'],'cli_sha256':manifest['cli']['sha256']})
        shim = shim_bytes(digest(raw),digest(pointer),digest(cli_raw))
        require(old_pointer in (None,pointer) and old_shim in (None,shim), 'FOREIGN_CURRENT_PRESERVED')
        require(optional(CURRENT) == old_pointer and optional(SHIM) == old_shim, 'CONTROL_PREIMAGE_CHANGED')
        static_files = {'owner_nox_fast_tools.py':cli_raw,'profile.json':assets[spec['profile_asset']],
                        'toolchain.lock.json':assets[spec['lock_asset']],'manifest.json':raw}
        for name,data in static_files.items():
            new_file(stage_release/name,data)
        expected_files = {name:digest(data) for name,data in static_files.items()}
        expected_files.update({str(Path(v['path']).relative_to(RELEASE)):v['sha256'] for v in tools.values()})
        phase('BEFORE_RELEASE_GUARD')
        require(guard() == baseline, 'BEFORE_RELEASE_GUARD')
        phase('RELEASE_PROMOTE')
        created = move_release_no_replace(stage_release)
        phase('RELEASE_VERIFY')
        verify_release(expected_files)
        receipt.update(release_created=created,manifest_sha256=digest(raw),tools=tools,
                       downloaded_archive_bytes=sum(r['size_bytes'] for r in rows),extracted_bytes=total[0])
        cli_fd = open_regular(RELEASE/'owner_nox_fast_tools.py',MIB)
        try:
            require(consume(cli_fd,MIB)[0] == digest(cli_raw), 'CLI_PIN')
            commands = [('status', ['status']),
                ('context',['context','--file','forge_split_guard.py','--symbol','bounded_split_lines','--lines','30']),
                ('search',['search','--pattern','bounded_split_lines','--file','forge_split_guard.py']),
                ('check',['check','--file','forge_split_guard.py'])]
            proofs = {}
            for label,tail in commands:
                phase({'status':'CLI_STATUS','context':'CLI_CONTEXT','search':'CLI_SEARCH','check':'CLI_CHECK'}[label])
                code,out = run_bounded([sys.executable,'-I','-B','/proc/self/fd/'+str(cli_fd),
                    '--manifest',str(RELEASE/'manifest.json'),'--manifest-sha256',digest(raw),*tail],
                    pass_fds=(cli_fd,),seconds=12)
                proof = strict_json(out)
                require(code == 0 and proof.get('schema') == 'NOX_FAST_TOOLS_RESULT_V1'
                        and proof.get('state') == 'READ_ONLY_RESULT', 'READ_ONLY_TOOL_PROOF')
                if label == 'status':
                    require(proof.get('binary_pins_verified') is True, 'TOOL_BINARY_PROOF')
                proofs[label] = {'state':'READ_ONLY_RESULT','output_sha256':digest(out),'output_bytes':len(out)}
        finally:
            os.close(cli_fd)
        phase('FINAL_PUBLICATION_GUARD')
        require(guard() == baseline and optional(CURRENT) == old_pointer and optional(SHIM) == old_shim,
                'FINAL_PUBLICATION_GUARD')
        # The shim fails closed until its exact current pointer exists.
        phase('CONTROL_PUBLISH')
        publish_equal_or_new(SHIM,shim,0o755)
        publish_equal_or_new(CURRENT,pointer)
        phase('PUBLISHED_READBACK')
        require(read(CURRENT) == pointer and read(SHIM) == shim and guard() == baseline, 'PUBLISHED_READBACK')
        phase('PERMANENT_ENTRYPOINT_PROOF')
        shim_fd = open_regular(SHIM,65536)
        try:
            require(consume(shim_fd,65536)[0] == digest(shim), 'SHIM_PIN')
            code,out = run_bounded(['/proc/self/fd/'+str(shim_fd),'status'],pass_fds=(shim_fd,),seconds=12)
            proof = strict_json(out)
            require(code == 0 and proof.get('schema') == 'NOX_FAST_TOOLS_RESULT_V1'
                    and proof.get('state') == 'READ_ONLY_RESULT'
                    and proof.get('binary_pins_verified') is True, 'PERMANENT_ENTRYPOINT_PROOF')
            proofs['permanent_entrypoint'] = {'state':'READ_ONLY_RESULT','output_sha256':digest(out),
                                             'output_bytes':len(out)}
        finally:
            os.close(shim_fd)
        phase('AFTER_TOOL_PROOFS_GUARD')
        require(guard() == baseline, 'AFTER_TOOL_PROOFS_GUARD')
        receipt.update(state='INSTALLED_AND_READ_ONLY_TOOLS_VERIFIED',manifest_path=str(RELEASE/'manifest.json'),
            current_path=str(CURRENT),cli_path=str(SHIM),cli_sha256=digest(shim),read_only_proofs=proofs,
            version_proofs=version_proofs,observed_config_sha256=sorted(observed_config_pins),
            native_processes_unchanged=True,protected_services_unchanged=True)
        phase('COMPLETE')
        return receipt
    except BaseException as exc:
        receipt.update(safe_failure(exc),failure_phase=diagnostic['phase'],
                       failure_operation=diagnostic['operation'])
        raise
    finally:
        if stage is not None:
            try:
                require(identity(os.stat(stage,follow_symlinks=False))[:2] == stage_identity, 'STAGING_IDENTITY')
                shutil.rmtree(stage.name,dir_fd=root_fd)
            except FileNotFoundError:
                pass
            except BaseException:
                receipt['staging_cleanup_verified'] = False
            else:
                receipt['staging_cleanup_verified'] = True
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(root_fd)
        receipt['elapsed_seconds'] = round(time.monotonic()-started,3)
        print('NOX_MAINT_ACCELERATION_INSTALL='+encoded(receipt).decode(),flush=True)


def main():
    diagnostic = {'phase':'ENTRY','operation':'NONE'}
    try:
        run(BUNDLE,SPEC,diagnostic)
    except BaseException as exc:
        # Covers the preflight before the transaction receipt exists, with no traceback.
        print('NOX_MAINT_ACCELERATION_DIAGNOSTIC='+encoded({
            'schema':'NOX_ACCELERATION_FAILURE_DIAGNOSTIC_V1',
            **diagnostic,**safe_failure(exc)}).decode(),flush=True)
        return 1
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
