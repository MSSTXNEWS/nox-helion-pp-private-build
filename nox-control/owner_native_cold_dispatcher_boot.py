"""Install the exact future-only dispatcher boot hook without a service operation."""
import os
import re
from pathlib import Path


STARTUP = Path('/root/onstart.sh')
STARTUP_PIN = 'b36b916aadc8bb6047108823bf7b86f00448deafd9f79a824a9f4924c1190507'
STARTUP_BACKUP = 'onstart.sh.nox-pre-dispatcher-b36b916aadc8'
MAX_STARTUP = 128 << 10
CANDIDATE_PIN = 'e3e79973beb6291f5d33c3e79cff12e7e849ddef2fb1e30b897ace9a3f695115'
BOOT_SOURCE = r'''import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from http.client import HTTPConnection

OLD_EPOCH = 167790899
MAIN = '/etc/supervisor/supervisord.conf'
HOLDER_SERVICE = 'nox-engram-cold-holder'
MODEL_SERVICE = 'nox-ds41-8098'
DISPATCHER_SERVICE = 'nox-dispatcher-t855u'
PINS = {
    MAIN: 'fcead12b4dcb7f56b31d223f1cfa89792bd6e8008f78708a831b41fab9ece25d',
    '/etc/supervisor/conf.d/nox-engram-cold-holder.conf': 'cc7a0c2ddb579005bf9a6cdd6ccac9e33f1010039f6b2fe984f1059655b036df',
    '/etc/supervisor/conf.d/nox-ds41-8098.conf': '07187b45fdeb8e1f8122e4fe47e797317a2db7feafea5e764564af0ad9f6f447',
    '/etc/supervisor/conf.d/nox-t855u.conf': '4c871669f0b6618221585592c80040acab1acdd6b3ff5d659229fc008d894e73',
    '/root/nox/ops/engram_cold_holder.py': '3ec79df376490c37300eb7ec78b5feb59463bc5abd976093331e5c305d4c62de',
    '/root/nox/ops/nox_boot_ds41_8098.sh': 'b280bc46218d37a1480680a3d842c9b53d71a3d567c07606a1fb54878188d777',
    '/root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh': '50a4e198bcfed2e7965220e897c349db50eb17dd9560243827c9a085923e6638',
}
NOX = Path('/root/nox')
QUEUE = NOX / 'state/dispatcher/state.json'
LEASE = NOX / 'state/owner_maintenance.lock'
STOP_NAMES = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
              'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
STOP_FILES = tuple(NOX / name for name in STOP_NAMES) + (Path('/workspace/NOX_STOP'),)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
SAFE_PATH = '/usr/local/bin:/usr/bin:/bin'
MIN_RESERVE = 2 * 1024 ** 3


class Hold(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def identity(info):
    return info.st_dev, info.st_ino


def stamp(info):
    return (identity(info), info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def trusted(info, kind):
    require(kind(info.st_mode) and (info.st_uid, info.st_gid) == (0, 0)
            and not info.st_mode & 0o022, 'UNTRUSTED_PATH')


@contextmanager
def parent(path):
    path = Path(path)
    with ExitStack() as stack:
        fd = os.open('/', DIR_FLAGS)
        stack.callback(os.close, fd)
        trusted(os.fstat(fd), stat.S_ISDIR)
        for part in path.parts[1:-1]:
            fd = os.open(part, DIR_FLAGS, dir_fd=fd)
            stack.callback(os.close, fd)
            trusted(os.fstat(fd), stat.S_ISDIR)
        yield fd, path.name


def regular_at(fd, name, limit):
    with os.fdopen(os.open(name, READ_FLAGS, dir_fd=fd), 'rb') as file:
        info = os.fstat(file.fileno())
        trusted(info, stat.S_ISREG)
        require(info.st_nlink == 1 and 0 < info.st_size <= limit, 'FILE_SCOPE')
        raw = file.read(info.st_size + 1)
        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(len(raw) == info.st_size and stamp(info) == stamp(os.fstat(file.fileno()))
                == stamp(current), 'FILE_CHANGED')
    return raw, info


def regular(path, limit):
    with parent(path) as (fd, name):
        return regular_at(fd, name, limit)[0]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def start_ticks(pid):
    with Path(f'/proc/{pid}/stat').open('rb') as file:
        raw = file.read(8193)
    require(len(raw) <= 8192, 'PID_STAT_SCOPE')
    return int(raw.rpartition(b') ')[2].split()[19])


def supervisor(operation, service):
    binary = shutil.which('supervisorctl', path=SAFE_PATH)
    require(binary is not None, 'SUPERVISORCTL_ABSENT')
    executable = Path(binary).resolve(strict=True)
    require(executable.is_relative_to('/usr'), 'SUPERVISORCTL_PATH')
    with parent(executable) as (fd, name):
        trusted(os.stat(name, dir_fd=fd, follow_symlinks=False), stat.S_ISREG)
    return subprocess.run([str(executable), '-c', MAIN, operation, service],
                          capture_output=True, text=True, timeout=30,
                          env={'PATH': SAFE_PATH, 'LANG': 'C', 'LC_ALL': 'C'})


def service_state(service):
    result = supervisor('status', service)
    match = re.fullmatch(re.escape(service) + r'\s+(RUNNING|STOPPED)\s+([^\r\n]+)',
                         result.stdout.strip())
    require(match is not None, 'SERVICE_STATUS')
    if match[1] == 'STOPPED':
        require(result.returncode in (0, 3), 'SERVICE_STATUS')
        return 'STOPPED', 0, 0
    pid = re.match(r'pid (\d+),', match[2])
    require(pid is not None and result.returncode == 0, 'SERVICE_RUNNING_STATUS')
    number = int(pid[1])
    return 'RUNNING', number, start_ticks(number)


def check_stop():
    require(not any(os.path.lexists(path) for path in STOP_FILES), 'STOP_OR_MAINTENANCE')


def check_pins():
    for path, pin in PINS.items():
        require(digest(regular(path, 128 << 10)) == pin, 'DEPENDENCY_PIN')


def idle_queue():
    raw = regular(QUEUE, 32 << 20)
    data = json.loads(raw)
    require(isinstance(data, dict), 'QUEUE_INVALID')
    tasks = data.get('tasks')
    require(isinstance(tasks, dict) and bool(tasks), 'QUEUE_INVALID')
    for row in tasks.values():
        require(isinstance(row, dict) and isinstance(row.get('status'), str), 'QUEUE_INVALID')
        lease = row.get('native_worker_lease')
        require(row['status'] != 'running' and (not lease or isinstance(lease, dict)
                and lease.get('phase') == 'SETTLED'), 'QUEUE_ACTIVE')
    return digest(raw)


@contextmanager
def owner_lease():
    with parent(LEASE) as (fd, name):
        lock = os.open(name, READ_FLAGS, dir_fd=fd)
        try:
            info = os.fstat(lock)
            trusted(info, stat.S_ISREG)
            require(info.st_nlink == 1, 'LOCK_SCOPE')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Hold('OWNER_BUSY') from error

            def check_lease():
                with parent(LEASE) as (current, current_name):
                    require(identity(os.fstat(fd)) == identity(os.fstat(current))
                            and stamp(info) == stamp(os.fstat(lock))
                            == stamp(os.stat(current_name, dir_fd=current, follow_symlinks=False)),
                            'LOCK_CHANGED')

            check_lease()
            yield check_lease
        finally:
            os.close(lock)


def reserve():
    limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
    used = int(Path('/sys/fs/cgroup/memory.current').read_text())
    require(0 <= used < limit and limit - used >= MIN_RESERVE, 'RAW_RESERVE')
    return limit - used


def boot_services():
    holder = service_state(HOLDER_SERVICE)
    model = service_state(MODEL_SERVICE)
    require(holder[0] == model[0] == 'RUNNING' and holder[1] != model[1]
            and holder[2] < model[2], 'HOLDER_MODEL_ORDER')
    http = HTTPConnection('127.0.0.1', 8098, timeout=2)
    try:
        http.request('GET', '/health')
        result = http.getresponse()
        raw = result.read(4097)
        require(result.status == 200 and len(raw) <= 4096
                and isinstance(json.loads(raw), dict) and json.loads(raw).get('status') == 'ok',
                'MODEL_HEALTH')
    finally:
        http.close()
    return holder, model


def future_boot():
    epoch = start_ticks(1)
    require(epoch != OLD_EPOCH, 'CURRENT_GENERATION')
    check_pins()
    end = time.monotonic() + 300
    while True:
        check_stop()
        try:
            ready = boot_services()
            reserve()
            break
        except (Hold, OSError, ValueError, subprocess.SubprocessError):
            if time.monotonic() >= end:
                raise Hold('READINESS_TIMEOUT') from None
            time.sleep(3)
    with owner_lease() as check_lease:
        check_pins()
        queue = idle_queue()
        state = service_state(DISPATCHER_SERVICE)
        if state[0] == 'RUNNING':
            return 'ALREADY_RUNNING'
        require(state[0] == 'STOPPED', 'DISPATCHER_NOT_STOPPED')
        require(ready == boot_services(), 'SERVICES_CHANGED')
        require(queue == idle_queue(), 'QUEUE_CHANGED')
        require(start_ticks(1) == epoch, 'GENERATION_CHANGED')
        check_lease()
        check_stop()
        reserve()
        result = supervisor('start', DISPATCHER_SERVICE)
        require(result.returncode == 0 and service_state(DISPATCHER_SERVICE)[0] == 'RUNNING',
                'START_CONFIRMATION')
        return 'DISPATCHER_RUNNING'


def boot_entry():
    try:
        print('NOX_COLD_DISPATCHER_' + future_boot())
    except Hold as error:
        print('NOX_COLD_DISPATCHER_HOLD_' + str(error))
    except (OSError, ValueError, IndexError, AttributeError, subprocess.SubprocessError):
        print('NOX_COLD_DISPATCHER_HOLD_DEPENDENCY_UNAVAILABLE')
'''


exec(compile(BOOT_SOURCE, '<nox-cold-dispatcher>', 'exec'))


def candidate(raw):
    require(digest(raw) == STARTUP_PIN and raw.endswith(b'\n'), 'STARTUP_PREIMAGE')
    require('NOX_COLD_DISPATCHER_BOOT' not in BOOT_SOURCE, 'HEREDOC_DELIMITER')
    compile(BOOT_SOURCE, '<nox-cold-dispatcher>', 'exec')
    snippet = ("\n# NOX dispatcher: start only after a subsequent healthy cold boot.\n"
               "(/usr/bin/python3 -I - <<'NOX_COLD_DISPATCHER_BOOT'\n"
               + BOOT_SOURCE + "\nboot_entry()\nNOX_COLD_DISPATCHER_BOOT\n) &\n")
    result = raw + snippet.encode('utf-8')
    checked = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-n'], input=result,
                             capture_output=True, timeout=5, env={'PATH': SAFE_PATH})
    require(checked.returncode == 0 and len(result) <= MAX_STARTUP, 'STARTUP_SYNTAX')
    return result


def exchange(fd, left, right):
    import ctypes

    library = ctypes.CDLL(None, use_errno=True)
    native = getattr(library, 'renameat2', None)
    require(native is not None, 'ATOMIC_EXCHANGE_UNAVAILABLE')
    native.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    native.restype = ctypes.c_int
    if native(fd, os.fsencode(left), fd, os.fsencode(right), 2):
        raise Hold('ATOMIC_EXCHANGE_FAILED')


def exact_at(fd, name, expected_raw, expected_info):
    raw, info = regular_at(fd, name, MAX_STARTUP)
    require(raw == expected_raw and identity(info) == identity(expected_info)
            and info.st_mode == expected_info.st_mode, 'EXACT_COMPARE')


def live_services():
    states = tuple(service_state(service) for service in (MODEL_SERVICE, DISPATCHER_SERVICE))
    require(all(service[0] == 'RUNNING' for service in states)
            and len({service[1] for service in states}) == len(states), 'LIVE_SERVICES')
    return states


def exact_parent(fd):
    with parent(STARTUP) as (current, _):
        require(identity(os.fstat(current)) == identity(os.fstat(fd)), 'DESTINATION_CHANGED')


def install():
    require(os.geteuid() == os.getegid() == 0 and start_ticks(1) == OLD_EPOCH, 'INSTALL_GENERATION')
    require(os.access('/usr/bin/python3', os.X_OK), 'BOOT_PYTHON_ABSENT')
    with owner_lease() as check_lease, parent(STARTUP) as (fd, name):
        check_stop()
        check_pins()
        queue = idle_queue()
        before = live_services()
        previous, original = regular_at(fd, name, MAX_STARTUP)
        require(original.st_mode & 0o111, 'STARTUP_NOT_EXECUTABLE')
        proposed = candidate(previous)
        require(digest(proposed) == CANDIDATE_PIN, 'STARTUP_CANDIDATE_PIN')
        created = False
        swapped = False
        prepared = None
        try:
            scratch = os.open(STARTUP_BACKUP,
                              os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                              0o600, dir_fd=fd)
            created = True
            with os.fdopen(scratch, 'wb') as output:
                prepared = os.fstat(output.fileno())
                require(output.write(proposed) == len(proposed), 'TEMP_SHORT_WRITE')
                output.flush()
                os.fchmod(output.fileno(), stat.S_IMODE(original.st_mode))
                os.fsync(output.fileno())
                prepared = os.fstat(output.fileno())
            exact_parent(fd)
            exact_at(fd, STARTUP_BACKUP, proposed, prepared)
            exact_at(fd, name, previous, original)
            require(before == live_services() and queue == idle_queue()
                    and start_ticks(1) == OLD_EPOCH, 'LIVE_IDENTITY_CHANGED')
            check_pins()
            check_stop()
            check_lease()
            exchange(fd, name, STARTUP_BACKUP)
            swapped = True
            os.fsync(fd)
            exact_parent(fd)
            exact_at(fd, name, proposed, prepared)
            exact_at(fd, STARTUP_BACKUP, previous, original)
            check_lease()
            require(before == live_services() and start_ticks(1) == OLD_EPOCH, 'LIVE_IDENTITY_CHANGED')
        except (Hold, OSError, ValueError, subprocess.SubprocessError):
            if swapped:
                try:
                    exact_parent(fd)
                    exact_at(fd, name, proposed, prepared)
                    exact_at(fd, STARTUP_BACKUP, previous, original)
                    exchange(fd, name, STARTUP_BACKUP)
                    os.fsync(fd)
                    exact_at(fd, name, previous, original)
                except (Hold, OSError) as error:
                    raise Hold('ROLLBACK_RECONCILIATION') from error
            if created and prepared is not None:
                current = os.stat(STARTUP_BACKUP, dir_fd=fd, follow_symlinks=False)
                require(identity(current) == identity(prepared), 'CLEANUP_RECONCILIATION')
                os.unlink(STARTUP_BACKUP, dir_fd=fd)
                os.fsync(fd)
            raise
    return {'decision': 'PASS_DURABLE_FUTURE_BOOT_HOOK', 'instance_id': 60509551,
            'pid1_start_ticks': OLD_EPOCH, 'onstart_sha256': CANDIDATE_PIN,
            'backup_sha256': STARTUP_PIN, 'model_same_generation': True,
            'dispatcher_same_generation': True, 'active_queue_claims_before_install': 0,
            'supervisor_start_stop_reload_calls': 0, 'provider_mutations': 0,
            'cold_launch_executed': False}


def main():
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    try:
        require(re.fullmatch('[0-9a-f]{40}', source) and re.fullmatch('[1-9][0-9]*', request),
                'OWNER_CONTEXT')
        result = install()
    except Hold as error:
        result = {'decision': 'HOLD_DURABLE_BOOT_' + str(error)}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        result = {'decision': 'HOLD_DURABLE_BOOT_DEPENDENCY_UNAVAILABLE'}
    print('NOX_MAINT_COLD_BOOT_RECEIPT=' + json.dumps(
        {**result, 'source_sha': source, 'request_id': request}, sort_keys=True), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
