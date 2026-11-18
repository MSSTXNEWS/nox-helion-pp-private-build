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
SCMP_ACT_ALLOW = 0x7fff0000
SCMP_CMP_MASKED_EQ = 7
CLONE_THREAD = 0x00010000


class RunnerHold(RuntimeError):
    pass


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
                     'pidfd_open', 'prlimit64', 'setpriority', 'ioprio_set',
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
    if os.getcwd() != '/work':
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
            'no_new_privs':True, 'seccomp_filter':True}


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
    os.environ.clear()
    os.environ.update({'PATH':'/usr/bin:/bin', 'HOME':'/tmp', 'TMPDIR':'/tmp',
                       'LANG':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1'})
    sys.dont_write_bytecode = True
    if spec['backend'] == 'chroot_seccomp':
        if os.getuid() != 0:
            raise RunnerHold('HOLD_PROJECT_SANDBOX_REQUIRES_ROOT')
        # All descriptors except the bounded parent's standard pipes are shut
        # before changing root; no inherited directory handle can escape it.
        os.closerange(3, 65536)
        os.chroot(spec['rootfs'])
        os.chdir('/work')
        os.setgroups([])
        os.setgid(spec['gid'])
        os.setuid(spec['uid'])
        sys.path[:] = ['/work', '/packages', '/python', '/python/lib-dynload']
    elif spec['backend'] == 'bwrap_seccomp':
        os.chdir('/work')
        sys.path.insert(0, '/work')
    else:
        raise RunnerHold('HOLD_PROJECT_SANDBOX_BACKEND')
    # Linux clears PDEATHSIG on credential changes. Reinstate it after the
    # permanent uid/gid drop and recheck the native worker before executing code.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise RunnerHold('HOLD_PROJECT_VERIFIER_PARENT')
    if spec['backend'] == 'chroot_seccomp' and os.getppid() != spec['worker_pid']:
        raise RunnerHold('HOLD_PROJECT_VERIFIER_PARENT')
    os.closerange(3, 65536)
    _limits(spec)
    _restrict_syscalls(lib)
    isolation = _self_test(spec)
    capture = BoundedText()
    started = time.monotonic()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        suite = unittest.TestSuite()
        for name in spec['modules']:
            module = importlib.import_module(name)
            location = Path(module.__file__).resolve()
            if not str(location).startswith('/work/'):
                raise RunnerHold('HOLD_PROJECT_TEST_MODULE_ORIGIN')
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        discovered = suite.countTestCases()
        if discovered < spec['min_tests']:
            raise RunnerHold('HOLD_PROJECT_EMPTY_TEST_SUITE')
        result = unittest.TextTestRunner(stream=capture, verbosity=1).run(suite)
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
