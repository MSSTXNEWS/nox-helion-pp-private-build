"""Source-pinned read-only native identity/auth helpers, no native app imports."""
from __future__ import annotations
import ast, configparser, contextlib, fcntl, hashlib, json, os, re, shlex, stat, subprocess, time
from pathlib import Path
import urllib.request
from p0_witness_protocol import Hold

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
SERVICE = 'nox-proxy'
LAUNCHER = Path('/opt/supervisor-scripts/nox-proxy.sh')
CONF_DIR = Path('/etc/supervisor/conf.d')
PROC = Path('/proc')
WORKSPACE_STOP = Path('/workspace/NOX_STOP')
PROXY = SCRIPTS / 'chat_proxy.py'

def command(args, timeout=12):
    if args != ['supervisorctl', 'status', SERVICE]:
        raise Hold('HOLD_WITNESS_SERVICE_MUTATION_FORBIDDEN')
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise Hold('HOLD_SUPERVISOR_STATUS_TIMEOUT') from None
    if len(done.stdout) > 65536 or len(done.stderr) > 65536:
        raise Hold('HOLD_SUPERVISOR_STATUS_SIZE')
    return done.returncode, done.stdout.decode('utf-8', 'replace')

def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_directory(path):
    path = Path(path)
    info = path.lstat()
    if path.resolve() != path or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise Hold('HOLD_DIRECTORY_OWNER_OR_TYPE')


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


def exact_common_import(tree):
    rows = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname == 'SECRETS' or alias.name == 'SECRETS' and alias.asname is None:
                    rows.append((node, alias))
    if not rows:
        return False
    if len(rows) != 1 or rows[0][0].module != 'common' or rows[0][0].level != 0 or rows[0][1].name != 'SECRETS' or rows[0][1].asname is not None:
        raise Hold('HOLD_SECRETS_IMPORT_UNSUPPORTED')
    return True


def resolve_password_path(source, source_path=PROXY, allowed_root=ROOT, *, common_source=None):
    """Interpret a tiny path AST grammar; no eval/exec/import or env expansion."""
    tree = ast.parse(source)
    def assignments(unit):
        result = {}
        for node in unit.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result.setdefault(target.id, []).append(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result.setdefault(node.target.id, []).append(node.value)
        return result
    assigned = {'proxy': assignments(tree)}
    common_import = exact_common_import(tree)
    if common_import and 'SECRETS' in assigned['proxy']:
        raise Hold('HOLD_DUPLICATE_SECRETS_BINDING')
    if common_source is not None:
        if not common_import:
            raise Hold('HOLD_UNREQUESTED_COMMON_SOURCE')
        assigned['common'] = assignments(ast.parse(common_source))
    readers = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == '_read_chat_password']
    if len(readers) != 1:
        raise Hold('HOLD_AUTH_READER_MISSING')
    body = [n for n in readers[0].body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    # Actual native helper has precisely an OSError -> empty-string fallback.
    if len(body) == 1 and isinstance(body[0], ast.Try):
        attempt = body[0]
        valid = (len(attempt.handlers) == 1 and not attempt.orelse and not attempt.finalbody)
        handler = attempt.handlers[0] if valid else None
        valid = (valid and isinstance(handler.type, ast.Name) and handler.type.id == 'OSError'
                 and handler.name is None and len(handler.body) == 1
                 and isinstance(handler.body[0], ast.Return) and isinstance(handler.body[0].value, ast.Constant)
                 and handler.body[0].value.value == '')
        if not valid:
            raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
        body = attempt.body
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    value = body[0].value
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == 'strip' and not value.args and not value.keywords):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    read = value.func.value
    if not (isinstance(read, ast.Call) and isinstance(read.func, ast.Attribute) and read.func.attr == 'read_text' and isinstance(read.func.value, ast.Name) and read.func.value.id == 'CHAT_PASSWORD_PATH' and not read.args):
        raise Hold('HOLD_AUTH_READER_UNSUPPORTED')
    for kw in read.keywords:
        if kw.arg != 'encoding' or not isinstance(kw.value, ast.Constant) or kw.value.value not in ('utf-8', 'utf8'):
            raise Hold('HOLD_AUTH_READER_ENCODING')
    resolving = set()
    dependencies = set()
    def evaluate(node, unit='proxy'):
        if isinstance(node, ast.Name):
            dependencies.add(node.id)
            if len(dependencies) > 64:
                raise Hold('HOLD_PATH_CHAIN_LIMIT')
            identity = (unit, node.id)
            if identity in resolving:
                raise Hold('HOLD_PATH_CYCLE')
            resolving.add(identity)
            if unit == 'proxy' and node.id == 'SECRETS' and common_import:
                if 'common' not in assigned:
                    raise Hold('HOLD_COMMON_SOURCE_REQUIRED')
                result = evaluate(ast.Name(id='SECRETS'), 'common')
                resolving.remove(identity)
                return result
            local = assigned[unit]
            if node.id not in local:
                raise Hold('HOLD_PATH_NAME')
            if len(local[node.id]) != 1:
                raise Hold('HOLD_DUPLICATE_PATH_BINDING')
            result = evaluate(local[node.id][0], unit)
            resolving.remove(identity)
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1 and not node.keywords:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return Path(arg.value)
            if isinstance(arg, ast.Name) and arg.id == '__file__':
                return Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            rhs = node.right
            if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str) and rhs.value and not Path(rhs.value).is_absolute() and '..' not in Path(rhs.value).parts:
                return evaluate(node.left, unit) / rhs.value
        # Exact Path(__file__).resolve().parents[1], interpreted statically.
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'parents':
            idx = node.slice
            call = node.value.value
            if isinstance(idx, ast.Constant) and idx.value == 1 and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'resolve' and not call.args and not call.keywords:
                inner = call.func.value
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == 'Path' and len(inner.args) == 1 and isinstance(inner.args[0], ast.Name) and inner.args[0].id == '__file__' and not inner.keywords):
                    unit_path = Path(source_path) if unit == 'proxy' else Path(source_path).with_name('common.py')
                    return unit_path.absolute().parents[1]
        raise Hold('HOLD_PATH_EXPRESSION')
    try:
        result = evaluate(ast.Name(id='CHAT_PASSWORD_PATH'))
        root = Path(allowed_root).absolute()
        if not result.is_absolute() or '..' in result.parts or result == root or root not in result.parents or result.resolve() != result:
            raise Hold('HOLD_AUTH_PATH_OUTSIDE_ROOT_OR_SYMLINK')
    except Hold as exc:
        # Identifiers only. Never source, evaluated values, paths or secret text.
        exc.dependency_identifiers = sorted(name for name in dependencies if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', name))[:32]
        raise
    return result


def full_turn_episode(user: str, assistant: str) -> Optional[str]:
    """Injective full-turn text inside remember's existing 8000-char budget.

    The explicit lengths distinguish delimiter-containing tuples. The final
    non-whitespace marker keeps raw trailing answer whitespace inside the
    record, so remember.strip() cannot silently remove it.
    """
    if not isinstance(user, str) or not isinstance(assistant, str):
        return None
    if len(user) + len(assistant) > 8000:
        return None
    header = f"Эпизод чата V2; вопрос={len(user)}; ответ={len(assistant)}.\nВопрос:\n"
    middle = "\nОтвет:\n"
    footer = "\nКонец эпизода V2."
    if len(header) + len(user) + len(middle) + len(assistant) + len(footer) > 8000:
        return None
    return header + user + middle + assistant + footer

