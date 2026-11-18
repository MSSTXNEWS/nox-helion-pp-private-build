"""Pinned four-file V24 dialog update, called only by the existing owner repair runner.

No model requests, app imports, new service, runtime flags or admission bypass.
The maintenance lock serializes cooperating writers. Existing priority/slot
checks are observations, not an atomic lease against a newly arriving chat;
the coordinator must supply the already authorized quiet maintenance window.
"""
from __future__ import annotations
import configparser
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
import time
import urllib.request

from native_v24_dialog_transform import TRANSFORMS, transform

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
SERVICE = 'nox-proxy'
LAUNCHER = Path('/opt/supervisor-scripts/nox-proxy.sh')
CONF_DIR = Path('/etc/supervisor/conf.d')
PROC = Path('/proc')
WORKSPACE_STOP = Path('/workspace/NOX_STOP')
ORDER = ('s03_memory.py', 'nox_v120_s03_owner_memory_views.py', 'nox_v29_chat_bridge.py', 'chat_proxy.py')
AGENT_SHA = '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa'
OPERATOR_BASE = '8b7f431f419a3618bed7a9442ccf1072a48e747a'
EXPECTED_LOCK_IDENTITY = {'dev': 36, 'ino': 59886214}
DEPENDENCY_SHA = {
    'agent_loop.py': AGENT_SHA,
    'owner_chat_stream.py': '2c4ae86d1d8e2113c8dbb55807f0d52890f098904ac2914f0b1383156ed7ea25',
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
}


class Hold(Exception):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_directory(path):
    path = Path(path)
    info = path.lstat()
    if path.resolve() != path or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise Hold('HOLD_DIRECTORY_OWNER_OR_TYPE')










def metadata_preflight():
    """Collect all current strict metadata failures before permissions or stop.

    Only fixed runtime paths and the same bounded Supervisor config set already
    read by program_config(); no source text, credentials or environment output.
    """
    rows, blockers = [], []
    def inspect(path, kind, limit=None, optional=False):
        path = Path(path)
        row = {'path': str(path), 'kind': kind, 'required': not optional}
        reasons = []
        try:
            info = path.lstat()
            row.update(uid=info.st_uid, gid=info.st_gid, mode_octal=oct(stat.S_IMODE(info.st_mode)), dev=info.st_dev, ino=info.st_ino,
                       size=info.st_size, realpath=str(path.resolve(strict=True)))
            if row['realpath'] != str(path): reasons.append('NONCANONICAL_PATH')
            if info.st_uid != os.geteuid(): reasons.append('OWNER')
            if not (stat.S_ISDIR(info.st_mode) if kind == 'directory' else stat.S_ISREG(info.st_mode)): reasons.append('TYPE')
            if limit is not None and info.st_size > limit: reasons.append('SIZE')
            if info.st_mode & 0o022: reasons.append('GROUP_OR_OTHER_WRITE')
        except (OSError, RuntimeError) as exc:
            row.update(error_type=type(exc).__name__, errno=getattr(exc, 'errno', None))
            reasons.append('UNKNOWN_METADATA')
        row['blockers'] = reasons
        rows.append(row)
        if reasons and not optional: blockers.append({'path': str(path), 'reasons': reasons})
        return row
    for path in (ROOT.parent, ROOT, SCRIPTS, STATE, STATE / 'priority', CONF_DIR.parent, CONF_DIR):
        inspect(path, 'directory')
    inspect(STATE / 'owner_maintenance.lock', 'file')
    for name in (*ORDER, *DEPENDENCY_SHA):
        inspect(SCRIPTS / name, 'file', 250000)
    for name, size in (('CHAT_ACTIVE', 64), ('MODE', 64), ('status.json', 32768)):
        inspect(STATE / 'priority' / name, 'file', size)
    try:
        configs = sorted(CONF_DIR.glob('*.conf'))
        if len(configs) > 150: raise Hold('HOLD_SUPERVISOR_CONFIG_LIMIT')
        for path in configs: inspect(path, 'file', 300000)
    except (OSError, Hold) as exc:
        blockers.append({'path': str(CONF_DIR), 'reasons': [str(exc) if isinstance(exc, Hold) else 'CONFIG_ENUMERATION_UNKNOWN']})
    launcher = inspect(LAUNCHER, 'file', 32000, optional=True)
    try:
        config = program_config()
        if 'launcher_sha256' in config:
            launcher['required'] = True
            if launcher['blockers']: blockers.append({'path': str(LAUNCHER), 'reasons': launcher['blockers']})
    except (OSError, Hold, configparser.Error, UnicodeError, ValueError) as exc:
        # Every possible strict-read path is included even when the binding
        # cannot yet be parsed. An unused optional launcher alone never blocks.
        blockers.append({'path': 'SUPERVISOR_NOX_PROXY_BINDING', 'reasons': [str(exc) if isinstance(exc, Hold) else type(exc).__name__]})
        if launcher['blockers']:
            launcher['required'] = 'UNKNOWN_UNTIL_CONFIG_VALID'
    return {'paths': rows, 'blockers': blockers, 'path_set_complete_for_current_strict_checks': True,
            'new_stage_backup_receipt_paths': 'EXCLUSIVE_CREATION_LATER_UNDER_VERIFIED_PARENTS', 'source_contents_exported': False}






def stable_read(path, limit=250000):
    path = Path(path)
    if path.resolve() != path:
        raise Hold('HOLD_SOURCE_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_uid != os.geteuid() or first.st_mode & 0o022 or first.st_size > limit:
            raise Hold('HOLD_SOURCE_OWNER_TYPE_OR_SIZE')
        raw = os.pread(fd, limit + 1, 0)
        after, current = os.fstat(fd), path.lstat()
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode')
        if len(raw) != first.st_size or any(getattr(first, k) != getattr(after, k) or getattr(first, k) != getattr(current, k) for k in keys):
            raise Hold('HOLD_SOURCE_CHANGED_DURING_READ')
        return raw, {k[3:]: getattr(first, k) for k in keys}
    finally:
        os.close(fd)


def write_new(path, raw, mode=0o600, uid=None, gid=None):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        if uid is not None:
            os.fchown(fd, uid, gid)
        os.fchmod(fd, stat.S_IMODE(mode))
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    if digest(stable_read(path)[0]) != digest(raw):
        raise Hold('HOLD_WRITE_READBACK')


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_receipt(path, report):
    # The first receipt is reserved with O_EXCL by run(); updates stay local.
    raw = json.dumps(report, sort_keys=True, separators=(',', ':')).encode()
    fd, tmp = tempfile.mkstemp(prefix='.owner-chat-receipt-', dir=STATE)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync_directory(STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def busy_lock_observation(info):
    """Bounded read-only diagnostics; no lease reset, signals or retry."""
    result = {'lock_dev': info.st_dev, 'lock_ino': info.st_ino, 'holders': [],
              'probe_writes': 0, 'signals': 0, 'second_lock_attempts': 0,
              'pid_namespace_binding': 'UNKNOWN_UNLESS_LOCAL_PID_IS_OBSERVED'}
    try:
        with (PROC / 'locks').open('rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            result['status'] = 'UNKNOWN_PROC_LOCKS_LIMIT'
            return result
        result['status'] = 'OBSERVED_PROC_LOCKS'
        wanted = (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)
        for line in raw.decode('ascii', 'strict').splitlines():
            fields = line.split()
            if len(fields) < 8 or fields[1] == '->': continue
            address = fields[5].split(':')
            if len(address) != 3: continue
            try:
                identity = (int(address[0], 16), int(address[1], 16), int(address[2], 10))
                pid = int(fields[4], 10)
            except ValueError:
                continue
            if identity != wanted: continue
            if len(result['holders']) >= 16:
                result['holders_truncated'] = True
                break
            holder = {'kernel_pid': pid, 'kind': fields[1] if fields[1] in ('FLOCK', 'POSIX', 'OFDLCK') else 'UNKNOWN',
                      'mode': fields[3] if fields[3] in ('READ', 'WRITE') else 'UNKNOWN'}
            try:
                row = process(pid) if pid > 0 else None
                if row:
                    holder.update(local_pid=row['pid'], start_ticks=row['start_ticks'], ppid=row['ppid'], pgrp=row['pgrp'], state=row['state'],
                                  argv_sha256=row['argv_sha256'], service=row['service'] if row['service'] in
                                  ('nox-proxy', 'nox-priority-arbiter', 'nox-dispatcher-t855u', 'nox-priority-scheduler', 'nox-selfheal') else 'UNKNOWN')
                else: holder['local_identity'] = 'UNKNOWN_NOT_VISIBLE_OR_EXITED'
            except (OSError, UnicodeError, ValueError, Hold):
                holder['local_identity'] = 'UNKNOWN_READ_FAILED'
            result['holders'].append(holder)
    except (OSError, UnicodeError) as exc:
        result.update(status='UNKNOWN_PROC_LOCKS_READ', error_type=type(exc).__name__)
    return result


@contextlib.contextmanager
def maintenance_lease():
    path = STATE / 'owner_maintenance.lock'
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        actual, expected = os.fstat(fd), path.lstat()
        if not stat.S_ISREG(actual.st_mode) or actual.st_uid != os.geteuid() or actual.st_mode & 0o022 or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise Hold('HOLD_MAINTENANCE_LOCK_IDENTITY')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            failure = Hold('HOLD_MAINTENANCE_BUSY')
            failure.lock_diagnostic = busy_lock_observation(actual)
            raise failure from None
        yield {'dev': actual.st_dev, 'ino': actual.st_ino}
    finally:
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Hold('HOLD_HTTP_REDIRECT')


def local_get(path):
    if path not in ('http://127.0.0.1:8098/slots', 'http://127.0.0.1:8080/health'):
        raise Hold('HOLD_HTTP_SCOPE')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(path, timeout=5) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise Hold('HOLD_HTTP_STATUS_OR_SIZE')
        return raw


def global_stop_guard():
    # Preserve every existing global STOP; never clear a flag or write priority.
    stops = (ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag',
             STATE / 'STOP', STATE / 'STOP.flag', STATE / 'stop.flag',
             ROOT / '.stop', ROOT / 'program/STOP', WORKSPACE_STOP,
             STATE / 'OWNER_MAINTENANCE.flag')
    for path in stops:
        try:
            path.lstat()  # A dangling symlink is still an explicit STOP.
        except FileNotFoundError:
            continue
        except OSError:
            raise Hold('HOLD_GLOBAL_STOP_UNKNOWN') from None
        raise Hold('HOLD_GLOBAL_STOP_REMAINS')


def owner_idle():
    global_stop_guard()
    priority = {}
    now = time.time()
    for name, expected in (('CHAT_ACTIVE', b'0'), ('MODE', b'IDLE')):
        raw, info = stable_read(STATE / 'priority' / name, 64)
        age = now - info['mtime_ns'] / 1e9
        if raw.strip() != expected or not -2 <= age <= 5:
            raise Hold('HOLD_OWNER_PRIORITY_BUSY_OR_STALE')
        priority[name] = raw.strip().decode('ascii')
    raw, info = stable_read(STATE / 'priority/status.json', 32768)
    status = json.loads(raw)
    if status.get('mode') != 'IDLE' or status.get('train_pause') is not False or not -2 <= now - info['mtime_ns'] / 1e9 <= 5:
        raise Hold('HOLD_OWNER_PRIORITY_STATUS_UNKNOWN')
    slots = json.loads(local_get('http://127.0.0.1:8098/slots'))
    if not isinstance(slots, list) or not 1 <= len(slots) <= 16:
        raise Hold('HOLD_MODEL_SLOT_SCHEMA')
    for slot in slots:
        if not isinstance(slot, dict) or slot.get('is_processing', slot.get('processing')) is not False:
            raise Hold('HOLD_MODEL_BUSY_OR_UNKNOWN')
    return {'priority': priority, 'status_sha256': digest(raw), 'status_age_seconds': round(now - info['mtime_ns'] / 1e9, 3),
            'free_model_slots': len(slots), 'atomic_owner_admission_lease': False}


def command(args, timeout=12):
    # This module has only status/stop/start for the already existing nox-proxy.
    if args not in (["supervisorctl", "status", SERVICE], ["supervisorctl", "stop", SERVICE], ["supervisorctl", "start", SERVICE]):
        raise Hold('HOLD_COMMAND_SCOPE')
    if args[1] in ('stop', 'start'):
        global_stop_guard()
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        if len(done.stdout) > 65536 or len(done.stderr) > 65536:
            raise Hold('HOLD_SUPERVISOR_OUTPUT_SIZE')
        return done.returncode, done.stdout.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired:
        raise Hold('HOLD_SUPERVISOR_TIMEOUT') from None


def service_state():
    rc, output = command(['supervisorctl', 'status', SERVICE])
    match = re.fullmatch(r'nox-proxy\s+(RUNNING|STOPPED|EXITED|STARTING|BACKOFF|STOPPING|FATAL)(?:\s+pid\s+(\d+),[^\r\n]*)?(?:\s+[^\r\n]*)?\s*', output)
    if not match:
        raise Hold('HOLD_SUPERVISOR_STATUS_SCHEMA')
    return {'state': match[1], 'pid': int(match[2]) if match[2] else None, 'rc': rc}


def program_config(reader=None):
    reader = reader or stable_read
    root = CONF_DIR
    paths = sorted(root.glob('*.conf'))
    if len(paths) > 150:
        raise Hold('HOLD_SUPERVISOR_CONFIG_LIMIT')
    found = []
    for path in paths:
        raw, _ = reader(path, 300000)
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(raw.decode())
        if parser.has_section('program:' + SERVICE):
            values = {key: parser.get('program:' + SERVICE, key, fallback='') for key in ('command', 'stopasgroup', 'killasgroup', 'stopwaitsecs', 'stopsignal', 'directory')}
            found.append({'path': str(path), 'sha256': digest(raw), 'values': values})
    if len(found) != 1:
        raise Hold('HOLD_SUPERVISOR_PROGRAM_NOT_UNIQUE')
    result = found[0]
    argv = shlex.split(result['values']['command'])
    if str(SCRIPTS / 'chat_proxy.py') not in argv:
        if str(LAUNCHER) not in argv:
            raise Hold('HOLD_SERVICE_COMMAND_SCOPE')
        raw, _ = reader(LAUNCHER, 32000)
        if str(SCRIPTS / 'chat_proxy.py').encode() not in raw:
            raise Hold('HOLD_SERVICE_LAUNCHER_BINDING')
        result['launcher_sha256'] = digest(raw)
    return result


def process(pid, *, details=True):
    try:
        path = PROC / str(pid)
        first = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
        result = {'pid': int(pid), 'state': first[0], 'ppid': int(first[1]), 'pgrp': int(first[2]), 'start_ticks': int(first[19])}
        if details:
            with (path / 'cmdline').open('rb') as stream:
                argv_raw = stream.read(65537)
            with (path / 'environ').open('rb') as stream:
                env_raw = stream.read(262145)
            if len(argv_raw) > 65536 or len(env_raw) > 262144:
                raise Hold('HOLD_PROCESS_METADATA_SIZE')
            argv = [s.decode('utf-8', 'strict') for s in argv_raw.split(b'\0') if s]
            env = dict(s.split(b'=', 1) for s in env_raw.split(b'\0') if b'=' in s)
            service = env.get(b'SUPERVISOR_PROCESS_NAME', env.get(b'PROC_NAME', b'')).decode('ascii', 'strict')
            result.update(service=service, script_bound=str(SCRIPTS / 'chat_proxy.py') in argv,
                          argv_sha256=digest(argv_raw), exe=os.readlink(path / 'exe'), cwd=os.readlink(path / 'cwd'))
        second = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
        if first[19] != second[19]:
            raise Hold('HOLD_PROCESS_IDENTITY_CHANGED')
        return result
    except (FileNotFoundError, ProcessLookupError):
        return None


def service_identity(allow_stopped=False):
    state, config = service_state(), program_config()
    if allow_stopped and state['state'] in ('STOPPED', 'EXITED'):
        return {'service': state, 'config': config, 'process': None}
    if state['state'] != 'RUNNING' or not state['pid']:
        raise Hold('HOLD_SERVICE_NOT_RUNNING')
    row = process(state['pid'])
    if not row or row['state'] == 'Z' or row['service'] != SERVICE or not row['script_bound']:
        raise Hold('HOLD_SERVICE_PROCESS_IDENTITY')
    if config['values']['stopasgroup'].lower() == 'true' or config['values']['killasgroup'].lower() == 'true':
        paths = list(PROC.iterdir())
        if len(paths) > 20000:
            raise Hold('HOLD_PROCESS_TABLE_LIMIT')
        for path in paths:
            if path.name.isdigit():
                other = process(int(path.name), details=False)
                if other and other['state'] != 'Z' and other['pgrp'] == row['pgrp']:
                    owned = process(other['pid'])
                    if not owned or owned['service'] != SERVICE or owned['exe'] != row['exe'] or not owned['script_bound']:
                        raise Hold('HOLD_SERVICE_GROUP_FOREIGN_ROLE')
    return {'service': state, 'config': config, 'process': row}


def require_same_service(before):
    current = service_identity(allow_stopped=before['process'] is None)
    # Scheduler states R/S may change without changing process identity.
    def identity(value):
        row = dict(value['process']) if value['process'] else None
        if row is not None:
            row.pop('state', None)
        return value['service'], value['config'], row
    if identity(current) != identity(before):
        raise Hold('HOLD_SERVICE_IDENTITY_CHANGED')


def require_stopped():
    if service_state()['state'] not in ('STOPPED', 'EXITED'):
        raise Hold('HOLD_SERVICE_NOT_STOPPED')


class FileTransaction:
    def __init__(self, request, rollback=False):
        self.stage = SCRIPTS / ('.owner-v24-dialog-' + request)
        # Native observation: ROOT/backup disappeared after creation, while the
        # protected stage and all staged files persisted. The remover is UNKNOWN.
        # Keep rollback originals inside this new transaction's own stage.
        self.backup = self.stage / 'originals'
        self.original, self.prepared, self.metadata, self.replaced = {}, {}, {}, []
        self.directory_metadata, self.backup_metadata = {}, {}
        self.rollback = rollback
        self.prepare_operation = None
        self.prepare_failure = None

    def preparing(self, operation, path):
        # Only caller-validated, fixed transaction paths; no source or argv.
        self.prepare_operation = {'operation': operation, 'path': str(path)}

    def prepare(self):
        try:
            self._prepare()
        except OSError as exc:
            allowed = {SCRIPTS, self.stage, self.backup}
            allowed.update(folder / name for folder in (SCRIPTS, self.stage, self.backup) for name in ORDER)
            filename = str(exc.filename) if exc.filename is not None else None
            self.prepare_failure = {'operation': self.prepare_operation, 'errno': exc.errno,
                                    'error_type': type(exc).__name__,
                                    'filename': filename if filename is None or filename in {str(p) for p in allowed} else 'OUTSIDE_OR_UNKNOWN_SCOPE'}
            raise

    def _prepare(self):
        # Verify and compile all four in memory before creating any candidate.
        for name in ORDER:
            self.preparing('READ_ORIGINAL', SCRIPTS / name)
            raw, info = stable_read(SCRIPTS / name)
            pins = TRANSFORMS[name]
            self.preparing('TRANSFORM_AND_COMPILE', SCRIPTS / name)
            if self.rollback and digest(raw) == pins['before_sha256'] and len(raw) == pins['before_bytes']:
                prepared = raw  # Explicit rollback also recovers a partial apply.
            else:
                prepared = transform(name, raw, rollback=self.rollback)
            self.original[name], self.prepared[name], self.metadata[name] = raw, prepared, info
        self.preparing('CREATE_STAGE_DIRECTORY', self.stage)
        self.stage.mkdir(mode=0o700)
        self.bind_directory(self.stage)
        self.preparing('SYNC_STAGE_PARENT', SCRIPTS)
        sync_directory(SCRIPTS)
        for name in ORDER:
            info = self.metadata[name]
            self.preparing('WRITE_AND_VERIFY_STAGE_FILE', self.stage / name)
            write_new(self.stage / name, self.prepared[name], info['mode'], info['uid'], info['gid'])
        self.preparing('SYNC_STAGE_DIRECTORY', self.stage)
        sync_directory(self.stage)
        for name in ORDER:
            self.preparing('VERIFY_STAGE_FILE', self.stage / name)
            if stable_read(self.stage / name)[0] != self.prepared[name]:
                raise Hold('HOLD_STAGE_READBACK')
        self.verify_directories()
        self.preparing('CREATE_TRANSACTION_ORIGINALS_DIRECTORY', self.backup)
        self.backup.mkdir(mode=0o700)
        self.bind_directory(self.backup)
        self.preparing('VERIFY_ORIGINALS_BEFORE_BACKUP', SCRIPTS)
        self.verify_current(self.original, identity=True)
        for name in ORDER:
            self.preparing('WRITE_AND_VERIFY_BACKUP_FILE', self.backup / name)
            write_new(self.backup / name, self.original[name])
            self.backup_metadata[name] = stable_read(self.backup / name)[1]
        self.preparing('SYNC_BACKUP_DIRECTORY', self.backup)
        sync_directory(self.backup)
        sync_directory(self.stage)
        self.verify_backups()

    def bind_directory(self, path):
        checked_directory(path)
        info = path.lstat()
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise Hold('HOLD_TRANSACTION_DIRECTORY_MODE')
        self.directory_metadata[path] = {key: getattr(info, 'st_' + key) for key in ('dev', 'ino', 'uid', 'gid', 'mode')}

    def verify_directories(self):
        for path, expected in self.directory_metadata.items():
            checked_directory(path)
            info = path.lstat()
            if any(getattr(info, 'st_' + key) != value for key, value in expected.items()):
                raise Hold('HOLD_TRANSACTION_DIRECTORY_DRIFT')

    def verify_backups(self):
        if set(self.directory_metadata) != {self.stage, self.backup}:
            raise Hold('HOLD_TRANSACTION_DIRECTORIES_INCOMPLETE')
        self.verify_directories()
        for name in ORDER:
            raw, info = stable_read(self.backup / name)
            if raw != self.original[name] or info != self.backup_metadata.get(name) or stat.S_IMODE(info['mode']) != 0o600:
                raise Hold('HOLD_BACKUP_HASH_OR_IDENTITY_DRIFT')

    def verify_current(self, expected, identity=False):
        for name in ORDER:
            raw, info = stable_read(SCRIPTS / name)
            if raw != expected[name] or identity and info != self.metadata[name]:
                raise Hold('HOLD_TARGET_DRIFT')

    def replace(self, quiescent):
        self.verify_current(self.original, identity=True)
        self.verify_backups()
        for name in ORDER:
            quiescent()
            self.verify_backups()
            raw, info = stable_read(SCRIPTS / name)
            if raw != self.original[name] or info != self.metadata[name]:
                raise Hold('HOLD_TARGET_DRIFT')
            if stable_read(self.stage / name)[0] != self.prepared[name]:
                raise Hold('HOLD_STAGE_DRIFT')
            os.replace(self.stage / name, SCRIPTS / name)
            self.replaced.append(name)
            sync_directory(SCRIPTS)
            if stable_read(SCRIPTS / name)[0] != self.prepared[name]:
                raise Hold('HOLD_TARGET_POST_READBACK')
        self.verify_current(self.prepared)

    def undo(self, quiescent):
        expected = {name: self.prepared[name] if name in self.replaced else self.original[name] for name in ORDER}
        self.verify_current(expected)
        self.verify_backups()
        for name in reversed(self.replaced):
            quiescent()
            self.verify_backups()
            if stable_read(self.backup / name)[0] != self.original[name] or stable_read(SCRIPTS / name)[0] != self.prepared[name]:
                raise Hold('HOLD_ROLLBACK_DRIFT')
            info = self.metadata[name]
            restore = self.stage / (name + '.restore')
            write_new(restore, self.original[name], info['mode'], info['uid'], info['gid'])
            os.replace(restore, SCRIPTS / name)
            sync_directory(SCRIPTS)
        self.verify_current(self.original)


def remember_lifetime(lifetimes, identity):
    row = identity.get('process')
    if row is not None:
        token = {'pid': row['pid'], 'start_ticks': row['start_ticks']}
        if token not in lifetimes:
            lifetimes.append(token)


def require_lifetimes_dead(lifetimes):
    for token in lifetimes:
        row = process(token['pid'], details=False)
        if row and row['start_ticks'] == token['start_ticks'] and row['state'] != 'Z':
            raise Hold('HOLD_KNOWN_PROXY_PROCESS_SURVIVES')


def start_and_verify(before, *, recovery=False, lifetimes=None, startup=None):
    # Restoring the previously working proxy after our proven stop must not be
    # stranded by an unrelated model slot or stale arbiter heartbeat. A fresh
    # explicit owner STOP and service identity checks always remain binding.
    global_stop_guard() if recovery else owner_idle()
    require_agent_binding()
    require_stopped()
    if lifetimes is None:
        lifetimes = []
        remember_lifetime(lifetimes, before)
    require_lifetimes_dead(lifetimes)
    if program_config() != before['config']:
        raise Hold('HOLD_SERVICE_CONFIG_DRIFT')
    if startup is None:
        startup = {'identity_pending': False}
    startup['identity_pending'] = True
    rc, _ = command(['supervisorctl', 'start', SERVICE], timeout=75)
    if rc:
        raise Hold('HOLD_SERVICE_START_FAILED')
    after = service_identity()
    remember_lifetime(lifetimes, after)  # Capture before health or any later failing check.
    startup['identity_pending'] = False
    if before['process'] and (after['process']['pid'], after['process']['start_ticks']) == (before['process']['pid'], before['process']['start_ticks']):
        raise Hold('HOLD_PROXY_NOT_RELOADED')
    local_get('http://127.0.0.1:8080/health')
    return after


def require_agent_binding():
    # Modern common requires its already-reviewed writer-generation handoff.
    # This legacy-only transaction must never restart that runtime implicitly.
    for name, expected in DEPENDENCY_SHA.items():
        if digest(stable_read(SCRIPTS / name)[0]) != expected:
            raise Hold('HOLD_LEGACY_COMMON_REQUIRED' if name == 'common.py' else 'HOLD_RUNTIME_DEPENDENCY_DRIFT')


def run(rollback=False):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[0-9a-f]{40}', source) or os.geteuid() != 0:
        raise Hold('HOLD_OWNER_REQUEST_CONTEXT')
    report = {'schema': 'NOX_V24_DIALOG_INSTALL_V1', 'request': request, 'source_sha': source,
              'mode': 'rollback' if rollback else 'install', 'service': SERVICE, 'operator_base': OPERATOR_BASE,
              'model_calls': 0, 'model_reloads': 0, 'auth_modified': False, 's03_source_modified': True, 'database_migrations': 0, 'permissions_changed': False,
              'used': False, 'accepted': False, 'loaded_module_memory_identity_verified': False,
              'owner_admission': 'EXISTING_SNAPSHOTS_PLUS_COORDINATED_QUIET_WINDOW_REQUIRED', 'steps': []}
    report['metadata_preflight'] = metadata_preflight()
    if report['metadata_preflight']['blockers']:
        report.update(status='HOLD_METADATA_PREFLIGHT', completed=False, installed=None,
                      writes=0, service_calls=0, permissions_changed=False)
        return report
    for path in (ROOT, SCRIPTS, STATE):
        checked_directory(path)
    receipt = STATE / ('owner_v24_dialog_' + request + '.json')
    tx = FileTransaction(request, rollback)
    stopped = False
    before = None
    lifetimes = []
    startup = {'identity_pending': False}
    with maintenance_lease() as lock:
        report['lock'] = lock
        if lock != EXPECTED_LOCK_IDENTITY:
            raise Hold('HOLD_MAINTENANCE_LOCK_PIN')
        global_stop_guard()
        require_agent_binding()  # Before receipt, stage, stop or source mutation.
        report['runtime_dependencies'] = dict(DEPENDENCY_SHA)
        def lease_identity():
            current = (STATE / 'owner_maintenance.lock').lstat()
            if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (lock['dev'], lock['ino']):
                raise Hold('HOLD_MAINTENANCE_LOCK_CHANGED')
        def quiescent():
            lease_identity()
            global_stop_guard()
            require_agent_binding()
            require_stopped()
            require_lifetimes_dead(lifetimes)
        write_new(receipt, b'{}\n')  # Single-use request; never replay after a crash.
        def step(name, **data):
            report['steps'].append({'phase': name, 'time': time.time(), **data})
            report['active_operation'] = {'operation': 'SAVE_RECEIPT', 'step': name, 'path': str(receipt)}
            save_receipt(receipt, report)
            report['active_operation'] = {'operation': 'AFTER_SAVED_STEP', 'step': name}
        try:
            for path in (ROOT, SCRIPTS, STATE):
                checked_directory(path)
            guard = owner_idle()
            before = service_identity(allow_stopped=rollback)
            remember_lifetime(lifetimes, before)
            if before['process']:
                local_get('http://127.0.0.1:8080/health')
            require_agent_binding()
            step('preflight', guard=guard, before=before)
            report['active_operation'] = {'operation': 'PREPARE_TRANSACTION'}
            tx.prepare()
            step('staged_verified_and_backed_up', files={name: {'before': digest(tx.original[name]), 'after': digest(tx.prepared[name])} for name in ORDER},
                 transaction_originals={'directories': {str(path): info for path, info in tx.directory_metadata.items()},
                                       'files': {name: {'sha256': digest(tx.original[name]), 'bytes': len(tx.original[name]),
                                                        'dev': tx.backup_metadata[name]['dev'], 'ino': tx.backup_metadata[name]['ino'],
                                                        'mode': oct(stat.S_IMODE(tx.backup_metadata[name]['mode']))} for name in ORDER}})
            owner_idle()
            lease_identity()
            require_same_service(before)
            require_agent_binding()
            tx.verify_current(tx.original, identity=True)
            tx.verify_backups()
            if before['process']:
                stopped = True  # A timeout may occur after Supervisor stopped it.
                rc, _ = command(['supervisorctl', 'stop', SERVICE], timeout=75)
                if rc:
                    raise Hold('HOLD_SERVICE_STOP_FAILED')
            else:
                stopped = True
            quiescent()
            if before['process']:
                old = process(before['process']['pid'])
                if old and old['start_ticks'] == before['process']['start_ticks'] and old['state'] != 'Z':
                    raise Hold('HOLD_OLD_PROXY_PROCESS_SURVIVES')
            owner_idle()
            step('proxy_stopped')
            tx.replace(quiescent)
            step('four_postimages_verified')
            require_agent_binding()
            lease_identity()
            after = start_and_verify(before, lifetimes=lifetimes, startup=startup)
            tx.verify_current(tx.prepared)
            step('proxy_reloaded', after=after)
            report.update(status='ROLLED_BACK_RELOADED' if rollback else 'APPLIED_RELOADED_USE_PENDING', installed=not rollback, completed=True)
        except BaseException as exc:
            report.update(status='HOLD', completed=False,
                          error=str(exc) if isinstance(exc, Hold) else 'HOLD_' + type(exc).__name__.upper())
            if tx.prepare_failure is not None:
                report['prepare_failure'] = tx.prepare_failure
            if isinstance(exc, OSError):
                report['os_error'] = {'errno': exc.errno, 'error_type': type(exc).__name__,
                                      'receipt_filename_matches': exc.filename == str(receipt)}
            if stopped and before is not None:
                try:
                    lease_identity()
                    global_stop_guard()
                    current = service_identity(allow_stopped=True)
                    remember_lifetime(lifetimes, current)
                    if current['process'] is not None:
                        startup['identity_pending'] = False
                    if startup['identity_pending']:
                        raise Hold('HOLD_PROXY_START_IDENTITY_UNKNOWN')
                    if current['config'] != before['config']:
                        raise Hold('HOLD_RECOVERY_CONFIG_DRIFT')
                    if current['process']:
                        # Startup could have succeeded before a later check failed.
                        # A running proxy may now be serving an owner: stopping
                        # it again still requires the full idle guard.
                        owner_idle()
                        require_same_service(current)
                        rc, _ = command(['supervisorctl', 'stop', SERVICE], timeout=75)
                        if rc:
                            raise Hold('HOLD_RECOVERY_STOP_FAILED')
                    quiescent()
                    if before['process']:
                        old = process(before['process']['pid'])
                        if old and old['start_ticks'] == before['process']['start_ticks'] and old['state'] != 'Z':
                            raise Hold('HOLD_OLD_PROXY_PROCESS_SURVIVES')
                    tx.undo(quiescent)
                    lease_identity()
                    restored = start_and_verify(before, recovery=True, lifetimes=lifetimes, startup=startup)
                    step('originals_restored_and_reloaded', after=restored)
                    report['recovery'] = 'PRE_OPERATION_BYTES_RESTORED_AND_RELOADED'
                except BaseException as recovery:
                    report['recovery'] = str(recovery) if isinstance(recovery, Hold) else 'HOLD_RECOVERY_' + type(recovery).__name__.upper()
                    report['manual_readback_required'] = True
            report['replaced_files'] = tx.replaced
        finally:
            report['known_proxy_lifetimes'] = list(lifetimes)
            report['startup_identity_pending'] = startup['identity_pending']
            report['files_after'] = {}
            for name in ORDER:
                try:
                    raw, info = stable_read(SCRIPTS / name)
                    report['files_after'][name] = {'sha256': digest(raw), 'bytes': len(raw)}
                except BaseException:
                    report['files_after'][name] = {'sha256': None, 'bytes': None}
            if all(report['files_after'][n]['sha256'] == TRANSFORMS[n]['after_sha256'] for n in ORDER):
                report['installed'] = True
            elif all(report['files_after'][n]['sha256'] == TRANSFORMS[n]['before_sha256'] for n in ORDER):
                report['installed'] = False
            else:
                report['installed'] = None
            save_receipt(receipt, report)
    return report


def entry(rollback=False):
    try:
        report = run(rollback=rollback)
    except BaseException as exc:
        report = {'schema': 'NOX_V24_DIALOG_INSTALL_V1', 'status': str(exc) if isinstance(exc, Hold) else 'HOLD_' + type(exc).__name__.upper(),
                  'completed': False, 'used': False, 'accepted': False, 'model_calls': 0, 'model_reloads': 0}
        if isinstance(exc, Hold) and hasattr(exc, 'lock_diagnostic'):
            report.update(lock_diagnostic=exc.lock_diagnostic, writes=0, service_calls=0, permissions_changed=False)
    # Public workflow logs receive hashes and fixed service fields, never a
    # Supervisor command line, environment contents or native source text.
    public = json.loads(json.dumps(report))
    for step in public.get('steps', []):
        for key in ('before', 'after'):
            if key in step and 'config' in step[key]:
                config = step[key]['config']
                values = config.pop('values')
                config['command_sha256'] = digest(values['command'].encode())
                config['stop_settings'] = {k: values[k] for k in ('stopasgroup', 'killasgroup', 'stopsignal', 'stopwaitsecs')}
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_v24_dialog', 'data': public}, separators=(',', ':')), flush=True)
    ok = report.get('completed') is True
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(ok).lower(), flush=True)
    return 0 if ok else 2
