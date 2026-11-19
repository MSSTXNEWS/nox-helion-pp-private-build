#!/usr/bin/env python3
"""Fixed isolated unittest runner. Candidate code is imported after confinement.

The coordinator starts this program either inside bwrap or before chroot. No
command, interpreter argument, shell fragment or host path comes from a model.
The final JSON describes source verification only, never project acceptance.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import errno
import fcntl
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import resource
import re
import signal
import socket
import stat
import sys
import time
import unittest

# These standard-library extension dependencies are loaded before a chroot. No
# candidate source is visible on sys.path yet (-I -S is required by the parent).
import sqlite3
import ssl
import math
import zlib
import _bz2
import _lzma
import _decimal
import _multiprocessing
import _posixsubprocess

REPORT_PREFIX = 'NOX_PROJECT_TEST_REPORT_V1:'
SANDBOX_WORK = '/work/project/source'
SCMP_ACT_ALLOW = 0x7fff0000
SCMP_CMP_MASKED_EQ = 7
CLONE_THREAD = 0x00010000


class RunnerHold(RuntimeError):
    pass


class KernelSelfFdAdapter:
    """Two live procfs file capabilities for this verifier, never a proc mount.

    Source code still parses its normal Path.read_text result. Every permitted
    read comes from the same real kernel file through pread(offset=0); no source
    bytes, fake proc file, snapshot response, directory fd or foreign PID is
    supplied. All other paths retain ordinary filesystem behavior.
    """
    BOOT_PATH = '/proc/sys/kernel/random/boot_id'
    PROC_MAGIC = 0x9fa0

    def __init__(self):
        self.pid = os.getpid()
        self.stat_path = '/proc/' + str(self.pid) + '/stat'
        self.entries = {}
        self.read_counts = {}
        self.start_ticks = None
        self.boot_sha256 = None
        self.original_read_text = None
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
        self.libc.fstatfs.restype = ctypes.c_int
        try:
            for path, bound in ((self.stat_path, 16384), (self.BOOT_PATH, 128)):
                fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                info = os.fstat(fd)
                self.entries[path] = (fd, info.st_dev, info.st_ino, bound)
                self.read_counts[path] = 0
                if not 3 <= fd < 96:
                    raise RunnerHold('HOLD_PROJECT_SELF_FD_NUMBER')
                self._checked_read(path)
            self.start_ticks = self.stat_fields(self._checked_read(self.stat_path))[2]
            self.boot_sha256 = hashlib.sha256(self._checked_read(self.BOOT_PATH)).hexdigest()
        except BaseException:
            self.close()
            raise

    @property
    def descriptors(self):
        return tuple(entry[0] for entry in self.entries.values())

    @staticmethod
    def stat_fields(raw):
        try:
            pid = int(raw.split(b' ', 1)[0])
            fields = raw.rsplit(b') ', 1)[1].split()
            ticks = int(fields[19])
            cpu_ticks = int(fields[11]) + int(fields[12])
            if ticks <= 0 or len(fields[0]) != 1:
                raise ValueError()
            return pid, fields[0].decode('ascii'), ticks, cpu_ticks
        except (ValueError, IndexError, UnicodeError) as exc:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_STAT_FORMAT') from exc

    def _check_fd(self, entry):
        fd, dev, ino, _ = entry
        try:
            info = os.fstat(fd)
            access = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
            fs = ctypes.create_string_buffer(256)
            if (not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (dev, ino)
                    or access != os.O_RDONLY or os.get_inheritable(fd)
                    or self.libc.fstatfs(fd, ctypes.byref(fs)) != 0
                    or ctypes.cast(fs, ctypes.POINTER(ctypes.c_long))[0] != self.PROC_MAGIC):
                raise RunnerHold('HOLD_PROJECT_SELF_FD_CAPABILITY')
        except OSError as exc:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_CLOSED_OR_CHANGED') from exc

    def _checked_read(self, path):
        if path not in self.entries or os.getpid() != self.pid:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_PATH_OR_PID')
        entry = self.entries[path]
        self._check_fd(entry)
        try:
            raw = os.pread(entry[0], entry[3] + 1, 0)
        except OSError as exc:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_KERNEL_READ') from exc
        self._check_fd(entry)
        if not raw or len(raw) > entry[3]:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_READ_BOUND')
        if path == self.stat_path:
            pid, _state, ticks, _cpu_ticks = self.stat_fields(raw)
            if pid != self.pid or self.start_ticks is not None and ticks != self.start_ticks:
                raise RunnerHold('HOLD_PROJECT_SELF_FD_IDENTITY_CHANGED')
        elif (re.fullmatch(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n?', raw) is None
              or self.boot_sha256 is not None and hashlib.sha256(raw).hexdigest() != self.boot_sha256):
            raise RunnerHold('HOLD_PROJECT_SELF_FD_BOOT_CHANGED')
        self.read_counts[path] += 1
        return raw

    def install(self):
        if self.original_read_text is not None:
            raise RunnerHold('HOLD_PROJECT_SELF_FD_ALREADY_INSTALLED')
        original = Path.read_text
        self.original_read_text = original
        def read_text(path, encoding=None, errors=None):
            literal = str(path)
            if literal in self.entries:
                return self._checked_read(literal).decode(encoding or 'utf-8', errors or 'strict')
            return original(path, encoding=encoding, errors=errors)
        Path.read_text = read_text

    def proof(self):
        if self.original_read_text is None or Path('/proc').exists() or Path('/proc').is_symlink():
            raise RunnerHold('HOLD_PROJECT_SELF_FD_CONFINEMENT_SCOPE')
        current = self.stat_fields(self._checked_read(self.stat_path))
        self._checked_read(self.BOOT_PATH)
        return {'schema':'NOX_KERNEL_SELF_FD_TEST_ADAPTER_V1',
                'mode':'KERNEL_SELF_FD_TEST_ADAPTER',
                'scope':'SELF_STAT_AND_BOOT_ID_ONLY', 'full_proc_available':False,
                'foreign_pid_visibility':False, 'kernel_backed':True,
                'fresh_pread_offset_zero':True, 'reserved_regular_file_descriptors':2,
                'directory_descriptors_preserved':0, 'procfs_magic':self.PROC_MAGIC,
                'verifier_pid':self.pid, 'verifier_parent_pid':os.getppid(),
                'start_ticks':self.start_ticks, 'own_pid_start_verified':True,
                'observed_process_state':current[1], 'boot_id_sha256':self.boot_sha256,
                'stat_reads':self.read_counts[self.stat_path],
                'boot_reads':self.read_counts[self.BOOT_PATH]}

    def close(self):
        if self.original_read_text is not None:
            Path.read_text = self.original_read_text
            self.original_read_text = None
        for entry in self.entries.values():
            fd, dev, ino, _ = entry
            try:
                info = os.fstat(fd)
                # Do not close an unrelated descriptor if candidate code has
                # already closed/replaced this capability. Reads fail closed.
                if (info.st_dev, info.st_ino) == (dev, ino):
                    os.close(fd)
            except OSError:
                pass
        self.entries.clear()


def close_unapproved_descriptors(adapter):
    keep = sorted(adapter.descriptors) if adapter is not None else []
    first = 3
    for fd in keep:
        os.closerange(first, fd)
        first = fd + 1
    os.closerange(first, 65536)


class ScmpArgCmp(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_uint),
                ('datum_a', ctypes.c_uint64), ('datum_b', ctypes.c_uint64)]


def _seccomp_library():
    name = ctypes.util.find_library('seccomp') or 'libseccomp.so.2'
    try:
        lib = ctypes.CDLL(name, use_errno=True)
    except OSError as exc:
        raise RunnerHold('HOLD_PROJECT_SECCOMP_UNAVAILABLE') from exc
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.c_int, ctypes.c_uint,
                                          ctypes.POINTER(ScmpArgCmp)]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    return lib


def _restrict_syscalls(lib):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RunnerHold('HOLD_PROJECT_NO_NEW_PRIVS')
    ctx = lib.seccomp_init(SCMP_ACT_ALLOW)
    if not ctx:
        raise RunnerHold('HOLD_PROJECT_SECCOMP_INIT')
    def deny(name, error=errno.EPERM, comparisons=None):
        number = lib.seccomp_syscall_resolve_name(name.encode())
        if number < 0:
            return
        values = (ScmpArgCmp * len(comparisons))(*comparisons) if comparisons else None
        if lib.seccomp_rule_add_array(ctx, 0x00050000 | error, number,
                                     len(comparisons or ()), values) != 0:
            raise RunnerHold('HOLD_PROJECT_SECCOMP_RULE')
    try:
        for name in ('socket', 'connect', 'bind', 'listen', 'accept',
                     'accept4', 'execve', 'execveat', 'fork', 'vfork',
                     'ptrace', 'process_vm_readv', 'process_vm_writev', 'mount',
                     'kill', 'tkill', 'tgkill', 'pidfd_send_signal', 'pidfd_getfd',
                     'rt_sigqueueinfo', 'rt_tgsigqueueinfo', 'process_madvise', 'process_mrelease',
                     'pidfd_open', 'setpriority', 'ioprio_set',
                     'sched_setparam', 'sched_setscheduler', 'sched_setattr',
                     'sched_setaffinity', 'migrate_pages', 'move_pages',
                     'umount2', 'pivot_root', 'chroot', 'unshare', 'setns',
                     'bpf', 'perf_event_open', 'userfaultfd', 'open_by_handle_at',
                     'name_to_handle_at', 'keyctl', 'add_key', 'request_key',
                     'reboot', 'kexec_load', 'kexec_file_load', 'init_module',
                     'finit_module', 'delete_module', 'swapon', 'swapoff',
                     'iopl', 'ioperm', 'io_uring_setup', 'io_uring_enter',
                     'io_uring_register'):
            deny(name)
        # getrlimit() uses prlimit64 on Linux. Permit only read-only queries of
        # this process (pid=0, new_limit=NULL); other processes and all writes
        # remain inaccessible after the hard limits have been installed.
        deny('prlimit64', comparisons=[ScmpArgCmp(0, 1, 0, 0)])
        deny('prlimit64', comparisons=[ScmpArgCmp(2, 1, 0, 0)])
        # libc may try clone3 for threads and fall back on ENOSYS. Ordinary
        # unittest threads are permitted, process creation is not.
        deny('clone3', errno.ENOSYS)
        # asyncio uses a private AF_UNIX self-pipe. No named socket can be
        # opened/connected, and inherited host descriptors are closed below.
        deny('socketpair', comparisons=[ScmpArgCmp(0, 1, socket.AF_UNIX, 0)])
        deny('clone', comparisons=[ScmpArgCmp(0, SCMP_CMP_MASKED_EQ, CLONE_THREAD, 0)])
        deny('prctl', comparisons=[ScmpArgCmp(0, 4, 1, 0)])  # Preserve parent-death signal.
        if lib.seccomp_load(ctx) != 0:
            raise RunnerHold('HOLD_PROJECT_SECCOMP_LOAD')
    finally:
        lib.seccomp_release(ctx)
    if libc.prctl(39, 0, 0, 0, 0) != 1 or libc.prctl(21, 0, 0, 0, 0) != 2:
        raise RunnerHold('HOLD_PROJECT_SECCOMP_READBACK')


def _limits(spec):
    memory = spec['memory_mb'] * 1024 * 1024
    for kind, value in ((resource.RLIMIT_AS, memory),
                        (resource.RLIMIT_CPU, spec['timeout_sec'] + 1),
                        (resource.RLIMIT_FSIZE, 8 * 1024 * 1024),
                        (resource.RLIMIT_NOFILE, 96),
                        (resource.RLIMIT_CORE, 0)):
        current = resource.getrlimit(kind)[1]
        limit = value if current == resource.RLIM_INFINITY else min(value, current)
        resource.setrlimit(kind, (limit, limit))


def _self_test(spec):
    if os.getuid() == 0 or os.geteuid() == 0 or os.getuid() != spec['uid']:
        raise RunnerHold('HOLD_PROJECT_SANDBOX_UID')
    if os.getcwd() != SANDBOX_WORK:
        raise RunnerHold('HOLD_PROJECT_SANDBOX_CWD')
    try:
        with open(spec['host_canary'], 'rb'):
            raise RunnerHold('HOLD_PROJECT_SANDBOX_HOST_VISIBLE')
    except (FileNotFoundError, PermissionError):
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except PermissionError:
        pass
    else:
        sock.close()
        raise RunnerHold('HOLD_PROJECT_SANDBOX_NETWORK')
    try:
        pid = os.fork()
    except PermissionError:
        pass
    else:
        if pid == 0:
            os._exit(91)
        os.waitpid(pid, 0)
        raise RunnerHold('HOLD_PROJECT_SANDBOX_FORK')
    # A missing filter would replace this runner and produce no valid report.
    try:
        os.execv('/usr/bin/true', ['/usr/bin/true'])
    except PermissionError:
        pass
    except FileNotFoundError:
        # chroot contains no executables; exec still has to be denied by seccomp.
        raise RunnerHold('HOLD_PROJECT_SANDBOX_EXEC_FILTER')
    return {'uid':os.getuid(), 'gid':os.getgid(), 'network_denied':True,
            'fork_denied':True, 'exec_denied':True, 'host_path_hidden':True,
            'no_new_privs':True, 'seccomp_filter':True, 'workdir':SANDBOX_WORK}


class BoundedText(io.TextIOBase):
    def __init__(self, maximum=32768):
        self.maximum = maximum
        self.kept = io.StringIO()
        self.total = 0
        self.digest = hashlib.sha256()
        self.tail = b''
    def write(self, value):
        value = str(value)
        raw = value.encode('utf-8', 'replace')
        self.digest.update(raw)
        self.tail = (self.tail + raw)[-8192:]
        if self.total < self.maximum:
            self.kept.write(raw[:self.maximum-self.total].decode('utf-8', 'replace'))
        self.total += len(raw)
        return len(value)
    def flush(self):
        return None


def run(spec):
    lib = _seccomp_library()
    if spec['backend'] == 'chroot_seccomp':
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != spec['worker_pid']:
            raise RunnerHold('HOLD_PROJECT_VERIFIER_PARENT')
    for path in reversed(spec.get('dependency_paths', [])):
        sys.path.insert(0, path)
    for name in spec.get('preload_modules', []):
        importlib.import_module(name)
    adapter = None
    try:
        if spec['backend'] == 'chroot_seccomp':
            if os.getuid() != 0:
                raise RunnerHold('HOLD_PROJECT_SANDBOX_REQUIRES_ROOT')
            # Only the verifier's standard pipes and two actual read-only
            # procfs files survive. Never retain a host directory descriptor.
            os.closerange(3, 65536)
            adapter = KernelSelfFdAdapter()
        return _run_confined(spec, lib, adapter)
    finally:
        if adapter is not None:
            adapter.close()


def _run_confined(spec, lib, adapter):
    os.environ.clear()
    os.environ.update({'PATH':'/usr/bin:/bin', 'HOME':'/tmp', 'TMPDIR':'/tmp',
                       'LANG':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1',
                       'MALLOC_ARENA_MAX':'2'})
    sys.dont_write_bytecode = True
    if spec['backend'] == 'chroot_seccomp':
        if os.getuid() != 0:
            raise RunnerHold('HOLD_PROJECT_SANDBOX_REQUIRES_ROOT')
        close_unapproved_descriptors(adapter)
        os.chroot(spec['rootfs'])
        os.chdir(SANDBOX_WORK)
        os.setgroups([])
        os.setgid(spec['gid'])
        os.setuid(spec['uid'])
        sys.path[:] = [SANDBOX_WORK, '/packages', '/python', '/python/lib-dynload']
    elif spec['backend'] == 'bwrap_seccomp':
        os.chdir(SANDBOX_WORK)
        sys.path.insert(0, SANDBOX_WORK)
    else:
        raise RunnerHold('HOLD_PROJECT_SANDBOX_BACKEND')
    # Linux clears PDEATHSIG on credential changes. Reinstate it after the
    # permanent uid/gid drop and recheck the native worker before executing code.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise RunnerHold('HOLD_PROJECT_VERIFIER_PARENT')
    if spec['backend'] == 'chroot_seccomp' and os.getppid() != spec['worker_pid']:
        raise RunnerHold('HOLD_PROJECT_VERIFIER_PARENT')
    close_unapproved_descriptors(adapter)
    _limits(spec)
    _restrict_syscalls(lib)
    if adapter is not None:
        adapter.install()
    isolation = _self_test(spec)
    if adapter is not None:
        isolation['kernel_self_fd_adapter'] = adapter.proof()
    capture = BoundedText()
    started = time.monotonic()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        suite = unittest.TestSuite()
        for name in spec['modules']:
            module = importlib.import_module(name)
            location = Path(module.__file__).resolve()
            if not str(location).startswith(SANDBOX_WORK + '/'):
                raise RunnerHold('HOLD_PROJECT_TEST_MODULE_ORIGIN')
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        discovered = suite.countTestCases()
        if discovered < spec['min_tests']:
            raise RunnerHold('HOLD_PROJECT_EMPTY_TEST_SUITE')
        result = unittest.TextTestRunner(stream=capture, verbosity=1).run(suite)
    if adapter is not None:
        # Recheck both live capabilities after all candidate imports/tests;
        # closed or replaced handles cannot yield a successful test report.
        isolation['kernel_self_fd_adapter'] = adapter.proof()
    return {'schema':'NOX_PROJECT_TEST_REPORT_V1', 'completed':True,
            'passed':result.wasSuccessful() and not result.skipped
                     and result.testsRun >= spec['min_tests'],
            'tests_run':result.testsRun, 'tests_discovered':discovered,
            'failures':len(result.failures), 'errors':len(result.errors),
            'skipped':len(result.skipped), 'elapsed_ms':round((time.monotonic()-started)*1000),
            'log_sha256':capture.digest.hexdigest(), 'log_bytes':capture.total,
            'output':re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', capture.tail.decode('utf-8', 'replace')),
            'failed_tests':[str(test)[:240] for test, _ in (result.failures + result.errors)][:64],
            'sandbox':isolation, 'modules':spec['modules']}


def main():
    try:
        if len(sys.argv) != 2:
            raise RunnerHold('HOLD_PROJECT_TEST_ARGUMENTS')
        with open(sys.argv[1], 'rb') as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise RunnerHold('HOLD_PROJECT_TEST_SPEC_SIZE')
        spec = json.loads(raw)
        report = run(spec)
    except BaseException as exc:
        report = {'schema':'NOX_PROJECT_TEST_REPORT_V1', 'completed':False,
                  'passed':False, 'reason':str(exc) if isinstance(exc, RunnerHold)
                  else 'HOLD_PROJECT_TEST_RUNNER_'+type(exc).__name__}
        if not isinstance(exc, RunnerHold):
            report['exception_detail'] = re.sub(r'[\x00-\x1f\x7f]', ' ', str(exc))[:300]
    print(REPORT_PREFIX + json.dumps(report, sort_keys=True, separators=(',', ':')), flush=True)
    return 0 if report.get('passed') is True else 2


if __name__ == '__main__':
    raise SystemExit(main())
